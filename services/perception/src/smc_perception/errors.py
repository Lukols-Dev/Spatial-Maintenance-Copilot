"""Why a request cannot be served, raised by the workspace code and answered by main.

The message is the response's "detail", shown to the user as it is: it names
files relative to the workspace root, never by absolute path.
"""

from pydantic import ValidationError


class WorkspaceError(Exception):
    """The workspace could not do what was asked; a bug or a broken disk if not a subclass."""

    status_code = 500


class NotFound(WorkspaceError):
    status_code = 404


class Conflict(WorkspaceError):
    """The request is fine, but the workspace is not in a state that allows it."""

    status_code = 409


class Invalid(WorkspaceError):
    status_code = 422


def describe(error: ValidationError) -> str:
    """A validation error on one line: where, then what, for every problem.

    Pydantic's own text spans lines and repeats the input, which may be a
    whole file.
    """
    problems = []
    for problem in error.errors(include_url=False, include_input=False):
        where = ".".join(str(part) for part in problem["loc"])
        message = problem["msg"].removeprefix("Value error, ")
        problems.append(f"{where}: {message}" if where else message)
    return "; ".join(problems)
