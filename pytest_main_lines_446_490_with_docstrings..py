# Check if collection path should be ignored based on patterns
ignore_paths = ignore_paths or []  # If ignore_paths is empty, assign an empty list.
excludeopt = config.getoption("ignore")  # Get the ignore option from command-line arguments.
if excludeopt:
    # Add additional paths to the ignore_paths list
    ignore_paths.extend(absolutepath(x) for x in excludeopt)

# If the collection path is in the ignore paths, we return True to indicate it should be ignored.
if collection_path in ignore_paths:
    return True

# Check for ignore glob patterns
ignore_globs = config._getconftest_pathlist(
    "collect_ignore_glob", path=collection_path.parent
)
ignore_globs = ignore_globs or []  # If ignore_globs is empty, assign an empty list.
excludeglobopt = config.getoption("ignore_glob")  # Get the ignore glob option from command-line arguments.
if excludeglobopt:
    # Add additional glob patterns to the ignore_globs list.
    ignore_globs.extend(absolutepath(x) for x in excludeglobopt)

# If the collection path matches any ignore glob pattern, we return True to ignore it.
if any(fnmatch.fnmatch(str(collection_path), str(glob)) for glob in ignore_globs):
    return True

# Check if the path is inside a virtual environment
allow_in_venv = config.getoption("collect_in_virtualenv")
if not allow_in_venv and _in_venv(collection_path):
    return True

# If the collection path is a directory, check if it matches the norecurse patterns.
if collection_path.is_dir():
    norecursepatterns = config.getini("norecursedirs")  # Get the norecurse patterns from configuration.
    if any(fnmatch_ex(pat, collection_path) for pat in norecursepatterns):
        return True

# If none of the above conditions are met, return None to indicate the path should be collected.
return None

# Function to collect directories from the filesystem.
def pytest_collect_directory(
    path: Path, parent: nodes.Collector
) -> nodes.Collector | None:
    """
    Collects files from the specified directory and returns a collector for that directory.

    Args:
        path (Path): The directory path to collect files from.
        parent (nodes.Collector): The parent collector object.

    Returns:
        nodes.Collector | None: Returns a directory collector or None if no files are collected.
    """
    return Dir.from_parent(parent, path=path)

# Function to modify collected items based on deselection criteria.
def pytest_collection_modifyitems(items: list[nodes.Item], config: Config) -> None:
    """
    Modify the collected items list based on deselection prefixes from the command line.

    Args:
        items (list): The list of collected test items.
        config (Config): The pytest configuration object.

    Returns:
        None: This function modifies the items list in place.
    """
    deselect_prefixes = tuple(config.getoption("deselect") or [])  # Get deselect prefixes from the config.
    if not deselect_prefixes:
        return

    remaining = []
    deselected = []
    for colitem in items:
        # If an item matches a deselect prefix, move it to the deselected list.
        if colitem.nodeid.startswith(deselect_prefixes):
            deselected.append(colitem)
        else:
            remaining.append(colitem)

    # If any items were deselected, update the list and notify through the pytest hook.
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining  # Update the items list with the remaining items.

# Proxy class to manage hook calls related to filesystem operations.
class FSHookProxy:
    def __init__(
        self,
        pm: PytestPluginManager,
        remove_mods: AbstractSet[object],
    ) -> None:
        """
        Proxy class to manage hook calls related to the file system.

        Args:
            pm (PytestPluginManager): The pytest plugin manager.
            remove_mods (AbstractSet[object]): A set of plugins to remove.
        """
        self.pm = pm
        self.remove_mods = remove_mods

    def __getattr__(self, name: str) -> pluggy.HookCaller:
        """
        Retrieves hook callers dynamically based on the hook name.

        Args:
            name (str): The name of the hook to retrieve.

        Returns:
            pluggy.HookCaller: The hook caller associated with the given hook name.
        """
        x = self.pm.subset_hook_caller(name, remove_plugins=self.remove_mods)
        self.__dict__[name] = x
        return x

# Exception class to handle interrupted test runs.
class Interrupted(KeyboardInterrupt):
    """Signals that the test run was interrupted."""

    __module__ = "builtins"  # For Python 3.

class Failed(Exception):
    """Signals that the test run should stop due to a failed test."""

# Cache class for storing and retrieving best relative paths to optimize performance.
@dataclasses.dataclass
class _bestrelpath_cache(dict[Path, str]):
    """
    Cache for storing best relative paths to optimize performance.

    Attributes:
        path (Path): The base path used for calculating relative paths.
    """
    __slots__ = ("path",)

    path: Path

    def __missing__(self, path: Path) -> str:
        """
        Retrieves the best relative path for a given path.

        Args:
            path (Path): The path for which to compute the best relative path.

        Returns:
            str: The best relative path.
        """
        r = bestrelpath(self.path, path)  # Calculate the best relative path.
        self[path] = r  # Store the result in the cache.
        return r

# Class for collecting files in a directory (extends nodes.Directory).
@final
class Dir(nodes.Directory):
    """Collector for files in a filesystem directory.

    .. versionadded:: 8.0

    .. note::
        This collector is responsible for gathering all files within a directory.
    """
