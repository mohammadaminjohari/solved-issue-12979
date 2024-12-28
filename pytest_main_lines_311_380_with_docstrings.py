
def pytest_collection(session: Session) -> None:
    """
    Trigger the collection process for the current test session.

    Args:
        session (Session): The pytest session object containing collected items.
    """
    session.perform_collect()


def pytest_runtestloop(session: Session) -> bool:
    """
    Execute the main loop for running tests.

    Handles the execution of collected test items and manages interrupts
    or failures during the process.

    Args:
        session (Session): The pytest session object.

    Returns:
        bool: True if collection-only mode is active; otherwise, execution continues.

    Raises:
        session.Interrupted: If collection errors or a manual stop condition occurs.
        session.Failed: If a stopping failure condition is met.
    """
    # Check for test collection failures and handle user-configured continuation.
    if session.testsfailed and not session.config.option.continue_on_collection_errors:
        raise session.Interrupted(
            f"{session.testsfailed} error{'s' if session.testsfailed != 1 else ''} during collection"
        )

    # Return early if only collecting tests, not running them.
    if session.config.option.collectonly:
        return True

    # Iterate through collected items and execute each test.
    for i, item in enumerate(session.items):
        nextitem = session.items[i + 1] if i + 1 < len(session.items) else None
        item.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)

        # Handle failure or stop conditions.
        if session.shouldfail:
            raise session.Failed(session.shouldfail)
        if session.shouldstop:
            raise session.Interrupted(session.shouldstop)
    return True


def _in_venv(path: Path) -> bool:
    """
    Check if the given path is the root of a virtual environment.

    This is done by verifying the existence of the `pyvenv.cfg` file or
    a `conda-meta/history` file in the given path.

    Args:
        path (Path): The directory path to check.

    Returns:
        bool: True if the directory is part of a virtual environment; False otherwise.

    Exceptions:
        OSError: If an OS-level error occurs during the check.
    """
    try:
        return (
            path.joinpath("pyvenv.cfg").is_file()
            or path.joinpath("conda-meta", "history").is_file()
        )
    except OSError:
        return False


def pytest_ignore_collect(collection_path: Path, config: Config) -> bool | None:
    """
    Determine if a given path should be ignored during test collection.

    This considers various factors such as ignored paths, virtual environments,
    and configured patterns to avoid during collection.

    Args:
        collection_path (Path): The path to check for collection exclusion.
        config (Config): The pytest configuration object.

    Returns:
        bool | None: True if the path should be ignored, False if it should not,
                     or None if no definitive decision can be made.
    """
    # Ignore `__pycache__` directories as they do not contain tests.
    if collection_path.name == "__pycache__":
        return True

    # Retrieve and check paths configured to be ignored.
    ignore_paths = config._getconftest_pathlist(
        "collect_ignore", path=collection_path.parent
    )
    