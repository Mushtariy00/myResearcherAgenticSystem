"""A try's answer: its code files from fenced blocks, the harness's choices from a JSON block, and
the checks that run before any GPU time.

Code inside a JSON string breaks: models escape it wrongly and lose its line breaks. So the answer
holds a ```python block per file, whose first line names it ("# file: model.py"), and one ```json
block with the choices. It is read leniently where models vary (```py, a heading that names the
file instead of the comment, prose around the blocks, a closing fence at the end of a block's last
line, files written without their fences but each after its comment) and strictly where it
matters: exactly one model.py, a loss.py only with "loss": "generated", files within the
checker's size, scalar kwargs.
An unusable answer raises InvalidModelOutputError, so StageAgents asks once for a corrected one.

The code's own names that start with one underscore (self._helper) are renamed (self.helper_):
the checker refuses such attributes, which reach other objects' private parts, and models write
their own all the time.
"""

import ast
import io
import json
import keyword
import math
import re
import textwrap
import tokenize
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

from agentic_core.codecheck import MAX_SOURCE_BYTES, check_module
from agentic_core.gpu_jobs import CODE_FILES, LOSS_FILE, MODEL_FILE
from agentic_core.schemas import NonEmptyStr
from agentic_worker.coding.config import ModelKwarg, TrainingChoices
from agentic_worker.llm_json import InvalidModelOutputError, parse_model_output

MODEL_CLASS = "Model"  # what the harness builds from model.py: Model(**model_kwargs)
LOSS_CLASS = "Loss"  # and from loss.py: Loss()
MAX_MODEL_KWARGS = 32  # CodeConfig.model_kwargs

type LossChoice = Literal["generated", "l1", "mse", "smooth_l1"]
GENERATED: LossChoice = "generated"
_LOSSES: dict[str, LossChoice] = {
    "generated": "generated",
    "l1": "l1",
    "mse": "mse",
    "smooth_l1": "smooth_l1",
}

_OPENING = re.compile(r"^[ \t]*(`{3,})[ \t]*([^`]*?)[ \t]*$")
_CLOSING = re.compile(r"^[ \t]*(`{3,})[ \t]*$")
# A closing fence at the end of a block's last line: '{"summary": ...}```'.
_GLUED_CLOSING = re.compile(r"^(.*[^`\s])[ \t]*(`{3,})[ \t]*$")
_LANGUAGE = re.compile(r"[\w+#-]*")
# The comment that names a block's file: "# file: model.py", "# filename = loss.py", "# model.py".
_FILE_COMMENT = re.compile(
    r"^#[ \t]*(?:(?:file(?:[ \t]*name)?|path)[ \t]*[:=][ \t]*)?`?([\w.-]+\.py)\b", re.IGNORECASE
)
_FENCE_FILE = re.compile(r"([\w.-]+\.py)\b", re.IGNORECASE)  # "```python model.py"
_HEADING_FILE = re.compile(r"\b(model|loss)\.py\b", re.IGNORECASE)  # "### model.py"
_PYTHON = frozenset({"", "python", "py", "python3", "py3"})
_JSON = frozenset({"json", "json5", "jsonc"})
# A name that starts with one underscore (_scale, _helper); two make a dunder, which stays refused.
_PRIVATE = re.compile(r"_[A-Za-z0-9]\w*")


@dataclass(frozen=True)
class Written:
    """A usable answer: the code files, and the choices the harness runs them with."""

    code: Mapping[str, str]  # model.py, then loss.py when "loss" is "generated"
    summary: str
    model_kwargs: Mapping[str, ModelKwarg]
    loss: LossChoice
    training: TrainingChoices

    @property
    def lines(self) -> int:
        return sum(source.count("\n") for source in self.code.values())

    def choices(self) -> str:
        """The choices as the answer's JSON block gives them, for a later prompt."""
        return choices_json(self.summary, self.model_kwargs, self.loss, self.training)


def choices_json(
    summary: str, model_kwargs: Mapping[str, ModelKwarg], loss: str, training: TrainingChoices
) -> str:
    return json.dumps(
        {
            "summary": summary,
            "model_kwargs": dict(model_kwargs),
            "loss": loss,
            "training": training.model_dump(),
        },
        indent=2,
        ensure_ascii=False,
    )


# --- reading the answer --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Block:
    info: str  # the opening fence's info string: "python", "py", "json", "python model.py", ...
    text: str
    before: str  # the last line of prose before it, a heading that may name its file

    @property
    def language(self) -> str:
        found = _LANGUAGE.match(self.info)
        return found.group(0).lower() if found else ""


class _Choices(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: NonEmptyStr
    model_kwargs: dict[str, Any] = Field(
        default_factory=dict, validation_alias=AliasChoices("model_kwargs", "kwargs")
    )
    loss: str | None = None
    training: dict[str, Any] = Field(default_factory=dict)

    @field_validator("summary", mode="before")
    @classmethod
    def _prose(cls, value: object) -> object:
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            value = " ".join(item.strip() for item in value)  # a list of points
        return value.replace("\0", "") if isinstance(value, str) else value

    @field_validator("model_kwargs", "training", mode="before")
    @classmethod
    def _none_is_empty(cls, value: object) -> object:
        return {} if value is None else value


def parse_answer(raw: str) -> Written:
    """The usable answer in ``raw``; InvalidModelOutputError says what makes it unusable."""
    blocks, prose = _blocks(raw.replace("\r\n", "\n").replace("\0", ""))
    named: dict[str, list[str]] = {}
    unnamed: list[str] = []
    choices: list[str] = []
    for block in blocks:
        if block.language in _JSON or (not block.language and block.text.lstrip()[:1] == "{"):
            choices.append(block.text)
            continue
        name, text = _file_name(block)
        if name is not None:
            named.setdefault(name, []).append(text)
        elif block.language in _PYTHON:
            unnamed.append(text)
        # A block in another language (a shell line, some output) is not a file.
    if not named and not unnamed:
        named = _unfenced_files(prose)
    unknown = sorted(set(named) - CODE_FILES)
    if unknown:
        raise InvalidModelOutputError(
            f"the answer has a block for {', '.join(unknown)}: write only model.py and, if the "
            "model needs a loss of its own, loss.py; the harness owns everything else"
        )
    if MODEL_FILE not in named and len(unnamed) == 1:
        named[MODEL_FILE] = unnamed  # the only code block, without its name
    if MODEL_FILE not in named:
        raise InvalidModelOutputError(
            'the answer has no model.py: put it in a ```python block whose first line is "# file: '
            'model.py"'
        )
    code = {name: _source(name, named[name]) for name in (MODEL_FILE, LOSS_FILE) if name in named}
    answer = _choices(choices, prose)
    code, kwargs = _own_names_public(code, _model_kwargs(answer.model_kwargs))
    return Written(
        code=code,
        summary=answer.summary,
        model_kwargs=kwargs,
        loss=_loss(answer.loss, LOSS_FILE in code),
        training=_training(answer.training),
    )


def _blocks(text: str) -> tuple[list[_Block], str]:
    """The fenced blocks of ``text``, and its prose: the lines outside them."""
    blocks: list[_Block] = []
    prose: list[str] = []
    body: list[str] | None = None
    fence = info = heading = before = ""
    for line in text.split("\n"):
        if body is None:
            opening = _OPENING.match(line)
            if opening is None:
                prose.append(line)
                before = line.strip() or before
            else:
                fence, info, heading, body = opening.group(1), opening.group(2), before, []
            continue
        closing = _CLOSING.match(line)
        glued = None if closing is not None else _GLUED_CLOSING.match(line)
        if closing is not None and len(closing.group(1)) >= len(fence):
            blocks.append(_Block(info, "\n".join(body), heading))
            body, before = None, ""
        elif glued is not None and len(glued.group(2)) >= len(fence):
            blocks.append(_Block(info, "\n".join([*body, glued.group(1)]), heading))
            body, before = None, ""
        else:
            body.append(line)
    if body is not None:
        raise InvalidModelOutputError("the answer ends inside a code block: it is incomplete")
    return blocks, "\n".join(prose)


def _unfenced_files(prose: str) -> dict[str, list[str]]:
    """Files written without their fences, each after the comment that names it ("# file:
    model.py") and up to the next one, or up to a "{" at the start of a line: the choices' JSON
    object, without its fence too. Taken only when each parses as Python once the comments and
    blank lines at its end are left out (they head what follows, such as "# JSON block"): else
    none, and the answer is asked for again."""
    files: dict[str, list[str]] = {}
    name: str | None = None
    lines: list[str] = []
    for line in [*prose.split("\n"), "# file: end.py"]:  # the last marker ends the last file
        marker = _FILE_COMMENT.match(line.strip())
        if marker is None and not line.startswith("{"):
            lines.append(line)
            continue
        if name is not None:
            while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):
                lines.pop()
            files.setdefault(name, []).append("\n".join(lines))
        name, lines = (marker.group(1).lower() if marker else None), []
    for texts in files.values():
        for text in texts:
            try:
                ast.parse(text)
            except SyntaxError:
                return {}
    return files


def _file_name(block: _Block) -> tuple[str | None, str]:
    """The file a block holds, and its text without the comment that named it.

    The comment on its first line names it; else a .py name in its fence, or, for a Python
    block, the one code file named in the line before it ("### model.py").
    """
    lines = block.text.split("\n")
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is not None:
        comment = _FILE_COMMENT.match(lines[first].strip())
        if comment is not None:
            return comment.group(1).lower(), "\n".join(lines[first + 1 :])
    in_fence = _FENCE_FILE.search(block.info)
    if in_fence is not None:
        return in_fence.group(1).lower(), block.text
    if block.language in _PYTHON:
        named = {name.lower() for name in _HEADING_FILE.findall(block.before)}
        if len(named) == 1:
            return f"{named.pop()}.py", block.text
    return None, block.text


def _source(name: str, texts: Sequence[str]) -> str:
    if len(texts) > 1:
        raise InvalidModelOutputError(
            f"the answer has {len(texts)} blocks for {name}; give exactly one"
        )
    source = textwrap.dedent(texts[0]).strip("\n").rstrip()  # a block indented in a list
    if not source:
        raise InvalidModelOutputError(f"the block for {name} is empty")
    source += "\n"
    size = len(source.encode())
    if size > MAX_SOURCE_BYTES:
        raise InvalidModelOutputError(
            f"{name} is {size} bytes, and the checker refuses files over {MAX_SOURCE_BYTES} "
            "bytes: make it shorter"
        )
    return source


def _own_names_public(
    code: Mapping[str, str], kwargs: Mapping[str, ModelKwarg]
) -> tuple[dict[str, str], dict[str, ModelKwarg]]:
    """The files with the one-underscore names each defines renamed, every use of them too
    (self._helper -> self.helper_), and model_kwargs' keys after model.py's. Only names a file
    defines (a def, a class, an argument, an assignment, self._x = ...) are renamed: one that
    reaches into another object (torch._C) stays, for the checker to refuse."""
    renamed: dict[str, str] = {}
    model_renames: dict[str, str] = {}
    for name, source in code.items():
        renames = _private_renames(source)
        renamed[name] = _rename(source, renames)
        if name == MODEL_FILE:
            model_renames = renames
    return renamed, {model_renames.get(key, key): value for key, value in kwargs.items()}


def _private_renames(source: str) -> dict[str, str]:
    """Each one-underscore name ``source`` defines, and the name it gets: of the same length, so
    the code keeps its layout (_helper -> helper_, else helper0 ...), and unused in the file. A
    name with no such free name keeps its own, and the checker says why."""
    try:
        tree = ast.parse(source)
        taken = {
            token.string
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type == tokenize.NAME
        }
    except (SyntaxError, tokenize.TokenError):
        return {}  # the checker reports it
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            defined.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            defined.add(node.attr)
        elif isinstance(node, ast.alias) and node.asname:
            defined.add(node.asname)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
    renames: dict[str, str] = {}
    for name in sorted(defined):
        if not _PRIVATE.fullmatch(name):
            continue
        stem = name[1:]
        candidates = [stem + "_", *(stem + digit for digit in "0123456789")]
        candidates += [letter + stem for letter in "pqvxz"]  # a stem that starts with a digit
        free = next(
            (
                candidate
                for candidate in candidates
                if candidate.isidentifier()
                and not keyword.iskeyword(candidate)
                and candidate not in taken
            ),
            None,
        )
        if free is not None:
            renames[name] = free
            taken.add(free)
    return renames


def _rename(source: str, renames: Mapping[str, str]) -> str:
    """``source`` with each name in ``renames`` replaced, token by token: strings and comments
    keep their text."""
    if not renames:
        return source
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    renamed = tokenize.untokenize(
        token._replace(string=renames.get(token.string, token.string))
        if token.type == tokenize.NAME
        else token
        for token in tokens
    )
    try:
        ast.parse(renamed)
    except SyntaxError:  # untokenize lost the layout: leave the names for the checker
        return source
    return renamed


def _choices(blocks: Sequence[str], prose: str) -> _Choices:
    if len(blocks) > 1:
        raise InvalidModelOutputError(
            f"the answer has {len(blocks)} JSON blocks; give exactly one, with the choices"
        )
    if blocks:
        return parse_model_output(blocks[0], _Choices)
    try:  # a JSON object written without its fence
        return parse_model_output(prose, _Choices)
    except InvalidModelOutputError:
        raise InvalidModelOutputError(
            'the answer has no ```json block with the choices: "summary", "model_kwargs", '
            '"loss" and "training"'
        ) from None


def _model_kwargs(given: Mapping[str, Any]) -> dict[str, ModelKwarg]:
    if len(given) > MAX_MODEL_KWARGS:
        raise InvalidModelOutputError(
            f'"model_kwargs" has {len(given)} entries; give at most {MAX_MODEL_KWARGS}'
        )
    kwargs: dict[str, ModelKwarg] = {}
    for name, value in given.items():
        if not name.isidentifier() or keyword.iskeyword(name):
            raise InvalidModelOutputError(
                f'"model_kwargs" has {json.dumps(name)}, which is not a Python argument name'
            )
        if isinstance(value, str):
            kwargs[name] = value.replace("\0", "")
        elif isinstance(value, bool | int) or (isinstance(value, float) and math.isfinite(value)):
            kwargs[name] = value
        else:
            raise InvalidModelOutputError(
                f'"model_kwargs.{name}" is {_kind(value)}: each value must be an int, a float, a '
                "string or a bool"
            )
    return kwargs


def _kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return "not a finite number"
    if isinstance(value, dict):
        return "an object"
    return "a list" if isinstance(value, list | tuple) else f"a {type(value).__name__}"


def _loss(given: str | None, has_loss_file: bool) -> LossChoice:
    if given is None:
        return GENERATED if has_loss_file else "l1"
    loss = _LOSSES.get(re.sub(r"[\s-]+", "_", given.strip().lower()))
    if loss is None:
        raise InvalidModelOutputError(
            f'"loss" is {json.dumps(given)}: give "generated" (with a loss.py) or one of the '
            'harness\'s losses, "l1", "mse" or "smooth_l1"'
        )
    if loss == GENERATED and not has_loss_file:
        raise InvalidModelOutputError('"loss" is "generated", but the answer has no loss.py')
    if loss != GENERATED and has_loss_file:
        raise InvalidModelOutputError(
            f'the answer has a loss.py, so "loss" must be "generated", not "{loss}"; or leave '
            f"loss.py out to train with the harness's {loss}"
        )
    return loss


def _training(given: Mapping[str, Any]) -> TrainingChoices:
    """The training settings, within the harness's bounds. Keys the harness owns (the epochs,
    the batch size, a schedule) are dropped."""
    values = {key: value for key, value in given.items() if key in TrainingChoices.model_fields}
    if isinstance(values.get("optimizer"), str):
        values["optimizer"] = values["optimizer"].strip().lower()  # "AdamW"
    if values.get("clip_grad_norm") in (0, False):  # "no clipping"
        values["clip_grad_norm"] = None
    try:
        return TrainingChoices.model_validate(values)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise InvalidModelOutputError(f'"training": {problems}') from exc


# --- the checks before any GPU time -------------------------------------------------------------


@dataclass(frozen=True)
class CodeFinding:
    """Why the checks refuse a file: the allowlist checker's (check.*) or the contract's
    (contract.*), at a 1-based line."""

    file: str
    line: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.file} line {self.line}: {self.code}: {self.message}"


def check_code(written: Written) -> list[CodeFinding]:
    """Why the code can't run, found before any GPU time: the allowlist checker's findings (the
    harness checks again when it loads the code), then the contract's, the class the harness
    builds from each file and the arguments it builds it with. Either would fail the smoke job,
    after its wait for the GPU."""
    findings: list[CodeFinding] = []
    for name, source in written.code.items():
        found = check_module(source, filename=name)
        findings += [CodeFinding(name, f.line, f.code, f.message) for f in found]
        try:
            tree = ast.parse(source, filename=name)
        except SyntaxError:
            continue  # the checker reported it
        given = written.model_kwargs if name == MODEL_FILE else {}
        findings += _contract(name, tree, given)
    return findings


def _contract(name: str, tree: ast.Module, given: Mapping[str, object]) -> list[CodeFinding]:
    symbol = MODEL_CLASS if name == MODEL_FILE else LOSS_CLASS
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == symbol]
    if not classes:
        return [
            CodeFinding(
                name, 1, "contract.class", f"{name} defines no top-level class {symbol}(nn.Module)"
            )
        ]
    inits = [
        node
        for node in classes[-1].body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    ]
    if not inits:
        return []  # inherited from a class of its own: the smoke test tries it
    init = inits[-1]
    return [
        CodeFinding(name, init.lineno, "contract.arguments", problem)
        for problem in _argument_problems(symbol, init.args, given)
    ]


def _argument_problems(symbol: str, args: ast.arguments, given: Mapping[str, object]) -> list[str]:
    """Why ``symbol(**given)`` would raise a TypeError: a keyword that __init__ has no parameter
    for, or a parameter without a default that ``given`` leaves out."""
    positional = [*args.posonlyargs, *args.args]
    if not positional:
        return []  # no self: the smoke test tells what is wrong
    first_default = len(positional) - len(args.defaults)
    keywords = {arg.arg for arg in [*args.args, *args.kwonlyargs] if arg is not positional[0]}

    def missing(parameter: str) -> str:
        if symbol == LOSS_CLASS:
            return f"Loss() is built without arguments, so {parameter!r} needs a default"
        return (
            f"Model.__init__ needs {parameter!r}, which model_kwargs does not give: add it there "
            "or give it a default"
        )

    problems: list[str] = []
    if args.kwarg is None:
        problems += [
            f"{symbol}.__init__ has no parameter {key!r}, which model_kwargs gives"
            for key in given
            if key not in keywords
        ]
    for index, arg in enumerate(positional[1:], start=1):
        if index >= first_default:
            continue
        if arg in args.posonlyargs:
            problems.append(
                f"{symbol}.__init__ takes {arg.arg!r} by position only, but the harness passes "
                "keyword arguments"
            )
        elif arg.arg not in given:
            problems.append(missing(arg.arg))
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        if default is None and arg.arg not in given:
            problems.append(missing(arg.arg))
    return problems
