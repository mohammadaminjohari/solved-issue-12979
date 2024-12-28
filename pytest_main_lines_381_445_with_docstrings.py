# Check for paths to be ignored
ignore_paths = ignore_paths or []  # If ignore_paths is empty, assign an empty list.
excludeopt = config.getoption("ignore")  # Get ignore options from command-line settings
if excludeopt:
    # Add additional paths to ignore_paths
    ignore_paths.extend(absolutepath(x) for x in excludeopt)

# If the collection path is in the ignore paths, we ignore it
if collection_path in ignore_paths:
    return True

# Check for glob patterns for paths to be ignored
ignore_globs = config._getconftest_pathlist(
    "collect_ignore_glob", path=collection_path.parent
)
ignore_globs = ignore_globs or []  # If ignore_globs is empty, assign an empty list.
excludeglobopt = config.getoption("ignore_glob")  # Get ignore_glob options from command-line settings
if excludeglobopt:
    # Add glob patterns to ignore_globs
    ignore_globs.extend(absolutepath(x) for x in excludeglobopt)

# If the collection path matches any of the glob patterns, we ignore it
if any(fnmatch.fnmatch(str(collection_path), str(glob)) for glob in ignore_globs):
    return True

# Check if the path is within a virtual environment
allow_in_venv = config.getoption("collect_in_virtualenv")
if not allow_in_venv and _in_venv(collection_path):
    return True

# If the collection path is a directory, check for directory ignore patterns
if collection_path.is_dir():
    norecursepatterns = config.getini("norecursedirs")  # Get directory ignore patterns
    if any(fnmatch_ex(pat, collection_path) for pat in norecursepatterns):
        return True

# If none of the above conditions match, collect the path
return None

# Function for collecting directories
def pytest_collect_directory(
    path: Path, parent: nodes.Collector
) -> nodes.Collector | None:
    """
    Collect files in a directory and return a collector for the directory.

    Args:
        path (Path): The directory path to collect from.
        parent (nodes.Collector): The parent collector.

    Returns:
        nodes.Collector | None: The directory collector or None if no collection happens.
    """
    return Dir.from_parent(parent, path=path)

# Function to modify the list of collected items based on deselect prefixes
def pytest_collection_modifyitems(items: list[nodes.Item], config: Config) -> None:
    """
    Modify collected items based on deselect prefixes.

    Args:
        items (list): The list of collected test items.
        config (Config): The pytest configuration object.

    Returns:
        None: Modifies the list in place.
    """
    deselect_prefixes = tuple(config.getoption("deselect") or [])  # Get deselect prefixes
    if not deselect_prefixes:
        return

    remaining = []
    deselected = []
    for colitem in items:
        # If the item matches a deselect prefix, remove it from the selected list
        if colitem.nodeid.startswith(deselect_prefixes):
            deselected.append(colitem)
        else:
            remaining.append(colitem)

    # If items were deselected, notify and update the list
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining  # Update the list of items

# Proxy class for managing filesystem hook calls
class FSHookProxy:
    def __init__(
        self,
        pm: PytestPluginManager,
        remove_mods: AbstractSet[object],
    ) -> None:
        """
        Proxy class for managing the file system hook calls.

        Args:
            pm (PytestPluginManager): The pytest plugin manager.
            remove_mods (AbstractSet[object]): Set of plugins to remove.
        """
        self.pm = pm
        self.remove_mods = remove_mods

    def __getattr__(self, name: str) -> pluggy.HookCaller:
        """
        Dynamically retrieves hook calls for the given name.

        Args:
            name (str): The name of the hook to retrieve.

        Returns:
            pluggy.HookCaller: The hook caller for the given hook.
        """
        x = self.pm.subset_hook_caller(name, remove_plugins=self.remove_mods)
        self.__dict__[name] = x
        return x

# Exception class for interrupted test runs
class Interrupted(KeyboardInterrupt):
    """Signals that the test run was interrupted."""

    __module__ = "builtins"  # For py3.

class Failed(Exception):
    """Signals a stop as failed test run."""

# Cache class for storing best relative paths for improved performance
@dataclasses.dataclass
class _bestrelpath_cache(dict[Path, str]):
    """
    Cache for storing best relative paths for improved performance.

    Attributes:
        path (Path): The base path for calculating relative paths.
    """
    __slots__ = ("path",)

    path: Path

    def __missing__(self, path: Path) -> str:
        """
        Retrieves the best relative path for a given path.

        Args:
            path (Path): The path to calculate the relative path for.

        Returns:
            str: The best relative path.
        """
        r = bestrelpath(self.path, path)
        self[path] = r
        return r

# Directory collector class for collecting files in a directory
@final
class Dir(nodes.Directory):
    """Collector of files in a file system directory.

    .. versionadded:: 8.0

    .. note::
        This collector is responsible for gathering all files within a directory.
    """
