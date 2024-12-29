def validate_basetemp(path: str) -> str:
    """
    Validate the provided `basetemp` path to ensure it is not empty, 
    the current working directory (cwd), or any ancestor of the cwd.

    Args:
        path (str): The path to validate.

    Returns:
        str: The validated path.

    Raises:
        argparse.ArgumentTypeError: If the path is invalid.
    """
    # GH 7119: Issue reference for additional context on the validation requirements.
    msg = "basetemp must not be empty, the current working directory or any parent directory of it"

    # Ensure the path is not empty.
    if not path:
        raise argparse.ArgumentTypeError(msg)

    def is_ancestor(base: Path, query: Path) -> bool:
        """
        Check if `query` is an ancestor of `base`.

        Args:
            base (Path): The base path to compare.
            query (Path): The potential ancestor path.

        Returns:
            bool: True if `query` is an ancestor of `base`, False otherwise.
        """
        if base == query:
            return True
        return query in base.parents

    # Ensure the path is not an ancestor of the current working directory (cwd).
    if is_ancestor(Path.cwd(), Path(path).absolute()):
        raise argparse.ArgumentTypeError(msg)

    # Check symlinks to ensure the resolved path is not an ancestor of cwd.
    if is_ancestor(Path.cwd().resolve(), Path(path).resolve()):
        raise argparse.ArgumentTypeError(msg)

    return path


def wrap_session(
    config: Config, doit: Callable[[Config, Session], int | ExitCode | None]
) -> int | ExitCode:
    """
    Run the main pytest session while managing initialization, 
    cleanup, and error handling.

    Args:
        config (Config): The pytest configuration object.
        doit (Callable): A callable that performs the main logic of the session.

    Returns:
        int | ExitCode: The exit status of the pytest session.
    """
    session = Session.from_config(config)  # Create a session from the configuration.
    session.exitstatus = ExitCode.OK
    initstate = 0  # Track initialization progress for error handling.

    try:
        try:
            config._do_configure()  # Configure pytest.
            initstate = 1
            config.hook.pytest_sessionstart(session=session)  # Trigger session start hooks.
            initstate = 2
            session.exitstatus = doit(config, session) or 0  # Run the main logic.
        except UsageError:
            session.exitstatus = ExitCode.USAGE_ERROR
            raise
        except Failed:
            session.exitstatus = ExitCode.TESTS_FAILED
        except (KeyboardInterrupt, exit.Exception):
            # Handle user interruption or pytest-specific exit exceptions.
            excinfo = _pytest._code.ExceptionInfo.from_current()
            exitstatus: int | ExitCode = ExitCode.INTERRUPTED
            if isinstance(excinfo.value, exit.Exception):
                if excinfo.value.returncode is not None:
                    exitstatus = excinfo.value.returncode
                if initstate < 2:
                    sys.stderr.write(f"{excinfo.typename}: {excinfo.value.msg}\n")
            config.hook.pytest_keyboard_interrupt(excinfo=excinfo)
            session.exitstatus = exitstatus
        except BaseException:
            # Handle unexpected exceptions.
            session.exitstatus = ExitCode.INTERNAL_ERROR
            excinfo = _pytest._code.ExceptionInfo.from_current()
            try:
                config.notify_exception(excinfo, config.option)
            except exit.Exception as exc:
                if exc.returncode is not None:
                    session.exitstatus = exc.returncode
                sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
            else:
                if isinstance(excinfo.value, SystemExit):
                    sys.stderr.write("mainloop: caught unexpected SystemExit!\n")
    finally:
        # Cleanup logic and session finalization.
        excinfo = None  # Explicitly break reference cycle.
        os.chdir(session.startpath)  # Restore original working directory.
        if initstate >= 2:
            try:
                config.hook.pytest_sessionfinish(
                    session=session, exitstatus=session.exitstatus
                )
            except exit.Exception as exc:
                if exc.returncode is not None:
                    session.exitstatus = exc.returncode
                sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        config._ensure_unconfigure()  # Ensure proper unconfiguration.

    return session.exitstatus


def pytest_cmdline_main(config: Config) -> int | ExitCode:
    """
    Main entry point for the pytest command line interface.

    Args:
        config (Config): The pytest configuration object.

    Returns:
        int | ExitCode: The exit status of the pytest session.
    """
    return wrap_session(config, _main)
