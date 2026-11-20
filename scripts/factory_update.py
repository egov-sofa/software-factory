#!/usr/bin/env python3
"""Keep a project made by the factory up to date with later factory versions: render a version for a project, update
the project to a newer one (a 3-way merge for the files it may edit), check that the files the factory owns are
untouched, and write the answers file for a project that has none
(docs/plans/2026-11-19-project-updates-and-shipped-standards.md).

Every file of a project has a kind, from templates/file-kinds.txt of the version being written: managed (the factory
owns it, an update replaces it), merged (both may edit it, an update merges) or seeded (the project owns it; only the
standards marker block inside it is updated). The project's answers live in .factory/answers.yml.

Usage:
  python3 scripts/factory_update.py render --ref <ref> --answers <file> --out <dir> [--factory <dir>]
      Render one factory version for one project, as that version's new-project.sh would have (without the git
      repository and the lockfile). Files listed in the answers' skip are left out.
  python3 scripts/factory_update.py update [--to <ref>] [--project <dir>] [--factory <dir>]
      Update the project from its recorded version to <ref> (default: the newest stable tag of its major version).
      Needs a clean working tree. Conflicts are left as markers in the files.
  python3 scripts/factory_update.py check [--project <dir>] [--factory <dir>]
      Exit 1 naming the managed files that differ from the recorded version; exit 3 when a newer release of the
      same major version exists (information, so CI can choose whether to fail on it).
  python3 scripts/factory_update.py adopt [--onboarded] [--set key=value ...] [--yes] [--project <dir>] [--factory <dir>]
      Infer the answers of a project that has no answers file and print them; with --yes, write them. --onboarded:
      the project was not made from a template, so the newest release is its base: the managed files and the
      standards are written, the marker blocks added, the template files it lacks listed in skip.

--project defaults to the current directory, --factory to the factory this script sits in (it needs the factory's
history and tags: git fetch --tags in the factory first).

Exit code 0 if all is well, 1 when an update left conflicts or check found a changed managed file, 2 on a usage error
or a refusal (nothing was changed), 3 when check finds a newer release. Standard library only.
"""
import argparse
import difflib
import fnmatch
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ".factory/answers.yml"
KINDS_FILE = "templates/file-kinds.txt"
KINDS = ("managed", "merged", "seeded")
# Kept identical to scripts/new-project.sh (the parity test renders every template both ways).
MANAGED_HEADER = "Managed by software-factory: /factory-update replaces this file. Change it in the factory, not here."
ANSWERS_COMMENT = '# Written by software-factory; /factory-update reads it. Edit only "skip".'
MARK_START = "<!-- software-factory:standards:start -->"
MARK_END = "<!-- software-factory:standards:end -->"
# The answers in the order new-project.sh writes them; _src_path and _commit are Copier's names, to keep that door open.
ANSWER_KEYS = ("_src_path", "_commit", "version", "template", "project_name", "package_name", "github_owner", "year",
               "onboarded", "skip")
STRING_KEYS = ("_src_path", "_commit", "version", "template", "project_name", "package_name", "github_owner", "year")
PLACEHOLDERS = (("{{PROJECT_NAME}}", "project_name"), ("{{PACKAGE_NAME}}", "package_name"),
                ("{{GITHUB_OWNER}}", "github_owner"), ("{{FACTORY_REPO}}", "_src_path"), ("{{YEAR}}", "year"))
UNKNOWN = "unknown"
STABLE_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
VERSION_GLOB = "v[0-9]*.[0-9]*.[0-9]*"   # release tags; the moving major tag (v1) does not match
PLAIN_RE = re.compile(r"^[A-Za-z_./][A-Za-z0-9_./-]*$")
TEMPLATE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]*$")   # as new-project.sh checks the name
PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESERVED = {"true", "false", "yes", "no", "on", "off", "null"}
SCAFFOLD_SUBJECT = "chore: scaffold from software-factory"
REMOTE_RE = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")
USES_RE = re.compile(r"uses:\s*([\w.-]+/[\w.-]+)/\.github/workflows/")


class Usage(Exception):
    """A usage error or a refusal: nothing was changed. Printed on stderr, exit 2."""


# ---- The answers file: a small YAML subset (key: value scalars, one list of strings), so no YAML library ----------

def yaml_value(value):
    """A string as new-project.sh writes it: plain when YAML can only read it as that string, else double-quoted."""
    if PLAIN_RE.match(value) and value.lower() not in RESERVED:
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _scalar(text, where):
    """One scalar: "double" (with \\ escapes), 'single', or plain up to a ' #' comment; true and false are booleans."""
    text = text.strip()
    if text[:1] == '"':
        m = re.match(r'"((?:[^"\\]|\\.)*)"\s*(?:#.*)?$', text)
        if not m:
            raise Usage(f"{where}: unterminated or malformed double-quoted value")
        return re.sub(r"\\(.)", r"\1", m.group(1))
    if text[:1] == "'":
        m = re.match(r"'((?:[^']|'')*)'\s*(?:#.*)?$", text)
        if not m:
            raise Usage(f"{where}: unterminated or malformed single-quoted value")
        return m.group(1).replace("''", "'")
    text = re.split(r"\s+#", text, maxsplit=1)[0].strip()
    if text[:1] in ("{", "&", "*", "!", "|", ">"):
        raise Usage(f"{where}: unsupported value '{text}' (only plain or quoted strings, true/false and one list)")
    if text in ("true", "false"):
        return text == "true"
    return text


def _inline_list(text, where):
    body = re.split(r"\]\s*(?:#.*)?$", text.strip()[1:], maxsplit=1)
    if len(body) != 2:
        raise Usage(f"{where}: unterminated list")
    items, current, quote = [], "", None
    for ch in body[0]:
        if quote:
            current += ch
            if ch == quote and not current.endswith("\\" + quote):
                quote = None
        elif ch in "\"'":
            quote, current = ch, current + ch
        elif ch == ",":
            items.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        items.append(current)
    values = [_scalar(item, where) for item in items if item.strip()]
    if any(not isinstance(v, str) for v in values):
        raise Usage(f"{where}: list items must be strings")
    return values


def parse_answers(text, name=ANSWERS):
    """The answers as a dict. Anything outside the subset (a nested map, a flow map, an anchor) is refused with the
    line, instead of guessed."""
    answers, current = {}, None
    for num, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        where = f"{name}:{num}"
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1] in (" ", "\t"):
            item = re.match(r"\s+-\s+(.*)$", line)
            if item and current is not None:
                value = _scalar(item.group(1), where)
                if not isinstance(value, str):
                    raise Usage(f"{where}: list items must be strings")
                answers[current].append(value)
                continue
            raise Usage(f"{where}: nested values are not supported here (only 'key: value' lines and one list of "
                        "strings, as '- item' lines)")
        m = re.match(r"([A-Za-z_][\w-]*):(?:\s+(.*))?$", line)
        if not m:
            raise Usage(f"{where}: expected 'key: value'")
        key, value = m.group(1), (m.group(2) or "").strip()
        if key in answers:
            raise Usage(f"{where}: duplicate key '{key}'")
        current = None
        if value == "" or value.startswith("#"):
            answers[key], current = [], key   # a block list may follow
        elif value.startswith("["):
            answers[key] = _inline_list(value, where)
        else:
            answers[key] = _scalar(value, where)
    return answers


def dump_answers(answers):
    lines = [ANSWERS_COMMENT]
    keys = [k for k in ANSWER_KEYS if k in answers] + [k for k in answers if k not in ANSWER_KEYS]
    for key in keys:
        value = answers[key]
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, list):
            lines.append(f"{key}: []" if not value else f"{key}:")
            lines += [f"  - {yaml_value(item)}" for item in value]
        else:
            lines.append(f"{key}: {yaml_value(str(value))}")
    return "\n".join(lines) + "\n"


def check_answers(answers, name=ANSWERS):
    for key in STRING_KEYS:
        if key not in answers:
            raise Usage(f"{name}: missing '{key}'")
        if not isinstance(answers[key], str):
            raise Usage(f"{name}: '{key}' must be a string (quote it)")
    if not isinstance(answers.get("skip", []), list):
        raise Usage(f"{name}: 'skip' must be a list of paths")
    if not isinstance(answers.get("onboarded", False), bool):
        raise Usage(f"{name}: 'onboarded' must be true or false")
    # The names become paths (the template folder, src/<package>/): the rules new-project.sh enforces, so an edited
    # answers file cannot reach outside the factory's templates or the project.
    for key, pattern, rule in (("template", TEMPLATE_RE, "lowercase letters, digits and dashes"),
                               ("project_name", PROJECT_RE, "lowercase letters, digits and dashes, starting with a "
                                                            "letter"),
                               ("package_name", PACKAGE_RE, "letters, digits and underscores, not starting with a "
                                                            "digit")):
        if not pattern.match(answers[key]):
            raise Usage(f"{name}: '{key}' must be {rule} (got '{answers[key]}')")
    return answers


def read_answers(project):
    path = Path(project) / ANSWERS
    if not path.is_file():
        raise Usage(f"{ANSWERS} not found in {project}: run `factory_update.py adopt` first")
    return check_answers(parse_answers(path.read_text(encoding="utf-8")))


# ---- File kinds and marker blocks ------------------------------------------------------------------------------

def parse_kinds(text):
    """The rules of file-kinds.txt as (kind, glob) pairs, in order."""
    rules = []
    for num, line in enumerate(text.splitlines(), 1):
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if len(parts) != 2 or parts[0] not in KINDS:
            raise Usage(f"{KINDS_FILE}:{num}: expected '<{'|'.join(KINDS)}> <glob>'")
        rules.append((parts[0], parts[1]))
    return rules


def kind_of(rel, rules):
    """The first matching rule's kind; seeded when none matches. fnmatchcase, like bash's [[ == ]], lets * match /."""
    return next((kind for kind, glob in rules if fnmatch.fnmatchcase(rel, glob)), "seeded")


def block_span(lines, name):
    """(start, end) line indexes of the marker block, None when there is none; a lone, doubled or reversed marker,
    or one sharing its line, is refused: replacing between broken markers could drop the project's own text."""
    starts = [i for i, line in enumerate(lines) if MARK_START in line]
    ends = [i for i, line in enumerate(lines) if MARK_END in line]
    if not starts and not ends:
        return None
    if (len(starts) == 1 and len(ends) == 1 and starts[0] < ends[0]
            and lines[starts[0]] == MARK_START and lines[ends[0]] == MARK_END):
        return starts[0], ends[0]
    raise Usage(f"{name} has broken software-factory standards markers: expected one '{MARK_START}' line, later one "
                f"'{MARK_END}' line, each on its own line. Fix or remove them by hand, then run this again. Nothing "
                "was changed.")


def with_block(text, block, name):
    """text with its marker block replaced by block (a list of lines, markers included), or block appended."""
    lines = text.split("\n")
    span = block_span(lines, name)
    if span is None:
        body = text.rstrip("\n")
        return (body + "\n\n" if body else "") + "\n".join(block) + "\n"
    return "\n".join(lines[:span[0]] + block + lines[span[1] + 1:])


def utf8(data, rel):
    """A file's text with LF endings; a file that is not UTF-8 is refused (its marker block cannot be edited safely)."""
    try:
        return lf(data).decode("utf-8")
    except UnicodeDecodeError:
        raise Usage(f"{rel} is not UTF-8 text (UTF-16?), so its standards block cannot be updated: save it as UTF-8, "
                    "then run this again. Nothing was changed.") from None


def block_of(data, name):
    """The marker block of a rendered file as a list of lines, or None."""
    lines = utf8(data, name).split("\n")
    span = block_span(lines, name)
    return None if span is None else lines[span[0]:span[1] + 1]


# ---- Rendering ---------------------------------------------------------------------------------------------------

def lf(data):
    return data.replace(b"\r\n", b"\n")


def executable(rel):
    """The files new-project.sh makes executable."""
    return rel.endswith(".sh") or rel == "scripts/check_content.py" or rel.startswith("scripts/hooks/")


def with_header(rel, data):
    """A managed file with the header that says so, exactly as new-project.sh adds it."""
    if rel.endswith(".md"):
        return f"<!-- {MANAGED_HEADER} -->\n".encode("utf-8") + data
    header = f"# {MANAGED_HEADER}\n".encode("utf-8")
    if data.startswith(b"#!"):
        end = data.find(b"\n")
        shebang, rest = (data + b"\n", b"") if end < 0 else (data[:end + 1], data[end + 1:])
        return shebang + header + rest
    return header + data


def files_under(folder):
    folder = Path(folder)
    return {p.relative_to(folder).as_posix(): p for p in sorted(folder.rglob("*")) if p.is_file()}


def sources(tree, template):
    """Project path -> source file of a factory tree, before placeholders: the shared layer, the template on top,
    the content guard and its hooks, and (versions that have file-kinds.txt) the standards."""
    tree = Path(tree)
    folder = (tree / "templates" / template).resolve()
    if (not TEMPLATE_RE.match(template) or folder.parent != (tree / "templates").resolve()
            or not folder.is_dir()):
        raise Usage(f"unknown template '{template}'")
    found = {}
    for layer in ("_shared", template):
        found.update(files_under(tree / "templates" / layer))
    found["scripts/check_content.py"] = tree / "scripts" / "check_content.py"
    for name, path in files_under(tree / "scripts" / "hooks").items():
        if "/" not in name:
            found[f"scripts/hooks/{name}"] = path
    if (tree / KINDS_FILE).is_file():
        for path in sorted((tree / "standards").glob("*.md")):
            found[f".factory/standards/{path.name}"] = path
    return found


def render_tree(tree, answers, commit=UNKNOWN, version=UNKNOWN):
    """Project path -> bytes of one factory tree rendered for the answers."""
    tree = Path(tree)
    shipped = (tree / KINDS_FILE).is_file()
    rules = parse_kinds((tree / KINDS_FILE).read_text(encoding="utf-8")) if shipped else []
    skip = set(answers.get("skip", []))
    out = {}
    for rel, path in sources(tree, answers["template"]).items():
        rel = rel.replace("{{PACKAGE_NAME}}", answers["package_name"])
        data = path.read_bytes()
        for placeholder, key in PLACEHOLDERS:
            data = data.replace(placeholder.encode("utf-8"), answers[key].encode("utf-8"))
        if shipped and kind_of(rel, rules) == "managed":
            data = with_header(rel, data)
        if rel not in skip:
            out[rel] = data
    if shipped:
        out[ANSWERS] = dump_answers({**answers, "_commit": commit, "version": version}).encode("utf-8")
    return out


def git(cwd, *args, check=True, binary=False):
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, check=False,
                          **({} if binary else {"text": True, "encoding": "utf-8", "errors": "replace"}))
    if check and done.returncode != 0:
        err = done.stderr if isinstance(done.stderr, str) else done.stderr.decode("utf-8", "replace")
        raise Usage(f"git {' '.join(args)} failed in {cwd}: {err.strip()}")
    return done if not check else done.stdout


def commit_of(factory, ref):
    out = git(factory, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}", check=False)
    return out.stdout.strip() if out.returncode == 0 else None


def version_of(factory, commit):
    """The release tag of a commit, or the newest one before it (git describe), or unknown."""
    out = git(factory, "describe", "--tags", "--abbrev=0", "--match", VERSION_GLOB, commit, check=False)
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else UNKNOWN


def export(factory, commit, dest):
    """The parts of a factory commit the renderer reads, from git archive (no checkout, so the clone is untouched)."""
    tops = set(git(factory, "ls-tree", "--name-only", commit).split())
    parts = sorted(tops & {"templates", "scripts", "standards"})
    if "templates" not in parts:
        raise Usage(f"{commit[:12]} of {factory} has no templates/ folder: not a software-factory commit")
    extract(git(factory, "archive", "--format=tar", commit, "--", *parts, binary=True), dest)


def extract(data, dest):
    """The regular files of a tar archive into dest. Folders are made as needed and links skipped (the factory has
    none); a member whose path would land outside dest (.., an absolute path, a drive letter) is refused."""
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            real = contained(dest, member.name)
            # ':' and '\' are refused on every system: Windows reads them as a drive and a separator
            if (real is None or ".." in Path(member.name).parts or Path(member.name).is_absolute()
                    or ":" in member.name or "\\" in member.name):
                raise Usage(f"refusing the factory archive: '{member.name}' would be written outside the render folder")
            Path(real).parent.mkdir(parents=True, exist_ok=True)
            Path(real).write_bytes(tar.extractfile(member).read())


def render(factory, ref, answers):
    """(files, commit, version) of one factory version rendered for the answers."""
    commit = commit_of(factory, ref)
    if not commit:
        raise Usage(f"'{ref}' is not a commit or tag of {factory} (git fetch --tags in the factory?)")
    version = ref if STABLE_RE.match(ref) else version_of(factory, commit)
    with tempfile.TemporaryDirectory(prefix="factory-render-") as tmp:
        export(factory, commit, tmp)
        return render_tree(tmp, answers, commit, version), commit, version


def rules_at(factory, commit):
    out = git(factory, "show", f"{commit}:{KINDS_FILE}", check=False)
    return parse_kinds(out.stdout) if out.returncode == 0 else None


def write_out(files, out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise Usage(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    for rel in files:
        inside(out, rel)   # every path checked before anything is written, as update does
    for rel, data in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if executable(rel):
            path.chmod(path.stat().st_mode | 0o111)


# ---- Versions --------------------------------------------------------------------------------------------------

def stable_tags(factory):
    """{tag: (major, minor, patch)} of the factory's release tags."""
    tags = {}
    for tag in git(factory, "tag", "--list", "v*").split():
        m = STABLE_RE.match(tag)
        if m:
            tags[tag] = tuple(int(x) for x in m.groups())
    return tags


def newest(factory, major=None):
    tags = {t: v for t, v in stable_tags(factory).items() if major is None or v[0] == major}
    return max(tags, key=tags.get) if tags else None


def version_tuple(version):
    m = STABLE_RE.match(version or "")
    return tuple(int(x) for x in m.groups()) if m else None


def major_of(version):
    found = version_tuple(version)
    return found[0] if found else None


def at_or_past(factory, older, newer):
    """True when commit `older` is `newer` or one of its ancestors (the project at `newer` already has it)."""
    if older == newer:
        return True
    return git(factory, "merge-base", "--is-ancestor", older, newer, check=False).returncode == 0


def base_ref(factory, answers, warn):
    """The commit the project was rendered from: _commit, else the tag in version (with a warning)."""
    commit = answers.get("_commit", UNKNOWN)
    if commit != UNKNOWN and commit_of(factory, commit):
        return commit_of(factory, commit)
    version = answers.get("version", UNKNOWN)
    if version != UNKNOWN and commit_of(factory, version):
        if commit != UNKNOWN:
            warn(f"the recorded commit {commit[:12]} is not in the factory's history; using the tag {version}")
        return commit_of(factory, version)
    raise Usage(f"cannot find the project's factory version (_commit {commit}, version {version}) in {factory}: "
                f"fetch the factory's tags (git fetch --tags), or set version in {ANSWERS} to the release the "
                "project was made from")


# ---- The project -----------------------------------------------------------------------------------------------

def contained(root, rel):
    """The real path of root/rel when it stays inside root, else None. Resolving it catches what the text of rel does
    not: a Windows drive letter, a backslash, a link in a parent folder."""
    real_root = os.path.realpath(root)
    real = os.path.realpath(os.path.join(real_root, rel))
    try:
        if os.path.commonpath([real_root, real]) != real_root:
            return None
    except ValueError:   # another drive on Windows
        return None
    return real


def inside(project, rel):
    """The project path of rel, refusing anything that would land outside the project, in its .git folder, or go
    through a symbolic link (a link committed in the project could point the write anywhere, such as .git/hooks)."""
    parts = Path(rel).parts
    if not rel or Path(rel).is_absolute() or ".." in parts:
        raise Usage(f"refusing to write '{rel}': not a path inside the project")
    current = Path(project)
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise Usage(f"refusing to write '{rel}': {current.relative_to(project).as_posix()} is a symbolic link. "
                        "Replace it with a regular file or folder, or list the file under skip in "
                        f"{ANSWERS}. Nothing was changed.")
    real = contained(project, rel)
    if real is None:
        raise Usage(f"refusing to write '{rel}': it leads outside the project")
    first = Path(os.path.relpath(real, os.path.realpath(project))).parts[0]
    if first.rstrip(". ").lower() == ".git":   # Windows ignores case and trailing dots and spaces
        raise Usage(f"refusing to write '{rel}': it is inside the project's .git folder")
    return Path(project) / rel


def read(project, rel):
    """The project's file, or None when it is missing. A dangling link is not missing: it is refused (writing the
    file would create the link's target, wherever it points)."""
    path = Path(project) / rel
    if path.is_symlink() and not path.exists():
        inside(project, rel)   # raises: a link
    return path.read_bytes() if path.is_file() else None


def clean_tree(project):
    """Refuse a working tree with changes, so an update's result is exactly the update; the answers file may be new
    (adopt just wrote it)."""
    if git(project, "rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        raise Usage(f"{project} is not a git repository")
    dirty = [line for line in git(project, "status", "--porcelain", "--untracked-files=all").splitlines()
             if line[3:].strip('"') != ANSWERS]
    if dirty:
        raise Usage("the working tree has changes; commit or stash them first:\n  " + "\n  ".join(dirty))


def set_executable(project, rel):
    path = Path(project) / rel
    path.chmod(path.stat().st_mode | 0o111)
    tracked = git(project, "ls-files", "--error-unmatch", "--", rel, check=False).returncode == 0
    # the index keeps the bit, also on Windows where the file system has none
    git(project, "update-index", *([] if tracked else ["--add"]), "--chmod=+x", "--", rel)


def merge(mine, base, theirs, labels):
    """(merged bytes, number of conflicts) of git merge-file on LF copies of the three versions."""
    with tempfile.TemporaryDirectory(prefix="factory-merge-") as tmp:
        names = []
        for name, data in (("project", mine), ("base", base), ("target", theirs)):
            (Path(tmp) / name).write_bytes(lf(data))
            names.append(str(Path(tmp) / name))
        done = subprocess.run(["git", "merge-file", "-p", "-L", labels[0], "-L", labels[1], "-L", labels[2], *names],
                              capture_output=True, check=False)
        if done.returncode < 0 or done.returncode > 127:
            raise Usage(f"git merge-file failed: {done.stderr.decode('utf-8', 'replace').strip()}")
        return done.stdout, done.returncode


class Summary:
    TITLES = (("replaced", "Replaced (managed)"), ("local", "Local changes replaced (managed)"),
              ("merged", "Merged"), ("conflicts", "Conflicts (markers left in the file)"), ("added", "Added"),
              ("removed", "Removed"), ("blocks", "Standards block updated"), ("decide", "Needs a decision"))

    def __init__(self):
        self.items = {key: [] for key, _ in self.TITLES}

    def add(self, key, text):
        self.items[key].append(text)

    def print(self, head):
        print(head)
        if not any(self.items.values()):
            print("  nothing to change")
        for key, title in self.TITLES:
            if self.items[key]:
                print(f"{title}:")
                for text in self.items[key]:
                    print(f"  {text}")


def plan_update(project, base, target, rules, labels):
    """(writes, deletes, summary): what the update does, decided before anything is written, so a refusal (a broken
    marker block) leaves the project untouched."""
    writes, deletes, s = {}, [], Summary()
    for rel in sorted(set(base) | set(target)):
        if rel == ANSWERS:
            continue
        kind = kind_of(rel, rules)
        if kind != "seeded":
            inside(project, rel)   # a link at a path the update may write or delete: refused before anything is written
        b, t, p = base.get(rel), target.get(rel), read(project, rel)
        if kind == "seeded":
            block = block_of(t, rel) if t is not None and p is not None else None
            if block:
                new = with_block(utf8(p, rel), block, rel).encode("utf-8")
                if new != lf(p):
                    writes[rel] = new
                    s.add("blocks", rel)
            continue
        if t is None:   # the factory removed it: delete what the project did not change
            if b is not None and p is not None:
                if lf(p) == lf(b):
                    deletes.append(rel)
                    s.add("removed", rel)
                else:
                    s.add("decide", f"{rel}: changed here, removed from the factory (kept)")
            continue
        if kind == "managed":
            if p is None or lf(p) != t:
                writes[rel] = t
                if p is None:
                    s.add("added", rel)
                elif b is None or lf(p) != lf(b):
                    s.add("local", rel)   # the project's copy was not the factory's: say what was lost
                else:
                    s.add("replaced", rel)
            continue
        # merged
        if p is None:
            if b is None:
                writes[rel] = t
                s.add("added", rel)
            elif lf(b) != t:
                s.add("decide", f"{rel}: deleted here, changed in the factory (not re-added)")
            continue
        if lf(p) == t:
            continue
        if b is None:
            s.add("decide", f"{rel}: exists here and is new in the factory, with different content (kept)")
            continue
        if lf(p) == lf(b):
            writes[rel] = t   # unchanged here: the factory's new version, no merge needed
            s.add("merged", rel)
        elif lf(b) == t:
            continue   # changed here only
        elif b"\0" in p + b + t:
            s.add("decide", f"{rel}: binary file changed in the factory and here (not merged)")
        else:
            merged, conflicts = merge(p, b, t, labels)
            writes[rel] = merged
            s.add("conflicts" if conflicts else "merged", f"{rel} ({conflicts} conflict(s))" if conflicts else rel)
    return writes, deletes, s


def apply(project, writes, deletes, rules):
    for rel in writes:
        inside(project, rel)
    for rel in deletes:
        inside(project, rel)
    for rel, data in writes.items():
        path = inside(project, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if kind_of(rel, rules) == "managed" and executable(rel):
            set_executable(project, rel)
    for rel in deletes:
        inside(project, rel).unlink()


def update(project, factory, to=None, out=print):
    answers = read_answers(project)
    clean_tree(project)
    warnings = []
    base_commit = base_ref(factory, answers, warnings.append)
    explicit = to is not None
    if to is None:
        major = major_of(answers.get("version"))
        if major is None:
            raise Usage(f"the recorded version is '{answers.get('version')}': give the release to update to with --to")
        to = newest(factory, major)
        if to is None:
            raise Usage(f"the factory has no v{major}.x.y release tag (git fetch --tags in the factory?)")
    target_commit = commit_of(factory, to)
    if not target_commit:
        raise Usage(f"'{to}' is not a commit or tag of {factory} (git fetch --tags in the factory?)")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    old = answers.get("version", UNKNOWN)
    if target_commit == base_commit:
        out(f"Already at {to}: nothing to update.")
        return 0
    # A project made from an untagged factory commit records the release before it (git describe), so the newest
    # release can be older than the project: rendering it would replace newer managed files with older ones and merge
    # the newer changes out, silently. Never move a project back.
    if at_or_past(factory, target_commit, base_commit):
        if not explicit:
            out(f"Already at or past {to} (the project was made from factory commit {base_commit[:12]}): nothing "
                "to update.")
            return 0
        raise Usage(f"--to {to} would move the project back from {base_commit[:12]} ({old}) to {to}, an older "
                    "factory commit. Nothing was changed.")
    rules = rules_at(factory, target_commit)
    if rules is None:
        raise Usage(f"{to} has no {KINDS_FILE}: it is older than updates and cannot be updated to")
    base, _, _ = render(factory, base_commit, answers)
    target, commit, version = render(factory, to, answers)
    writes, deletes, summary = plan_update(project, base, target, rules,
                                           ("project", f"factory {old}", f"factory {version}"))
    writes[ANSWERS] = dump_answers({**answers, "_commit": commit, "version": version}).encode("utf-8")
    apply(project, writes, deletes, rules)
    summary.print(f"software-factory update {old} -> {version}")
    return 1 if summary.items["conflicts"] else 0


def check(project, factory, out=print):
    answers = read_answers(project)
    warnings = []
    commit = base_ref(factory, answers, warnings.append)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    rendered, _, version = render(factory, commit, answers)
    rules = rules_at(factory, commit) or []
    changed = []
    for rel, data in sorted(rendered.items()):
        if kind_of(rel, rules) != "managed":
            continue
        mine = read(project, rel)
        if mine is None:
            changed.append(f"{rel} (missing)")
        elif lf(mine) != lf(data):
            changed.append(rel)
    recorded = answers.get("version", UNKNOWN)
    if changed:
        print(f"Managed files that differ from software-factory {recorded} (run /factory-update to restore them, "
              "and make the change in the factory instead):", file=sys.stderr)
        for rel in changed:
            print(f"  {rel}", file=sys.stderr)
        return 1
    major = major_of(recorded)
    latest = newest(factory, major) if major is not None else None
    if major is None:
        out(f"Managed files match the recorded factory commit; its release is {recorded}, so no newer one is looked for.")
        return 0
    if latest is None:
        out(f"Managed files match software-factory {recorded}; the factory has no v{major} release tag to compare with.")
        return 0
    latest_commit = commit_of(factory, latest)
    # Behind only when the project's commit does not contain the newest release (the version line alone would call a
    # project made from a commit after the release "behind" or "at" it)
    if not at_or_past(factory, latest_commit, commit):
        out(f"Managed files match software-factory {recorded}; {latest} is available: run /factory-update.")
        return 3
    if latest_commit == commit:
        out(f"Managed files match software-factory {latest}, the newest v{major} release here.")
    else:
        out(f"Managed files match the recorded factory commit {commit[:12]}, which is past {latest}, the newest "
            f"v{major} release here.")
    return 0


# ---- adopt -----------------------------------------------------------------------------------------------------

def tag_dates(factory):
    """{release tag: creation time} (the tagger's date, or the commit's for a lightweight tag)."""
    dates = {}
    for line in git(factory, "for-each-ref", "--format=%(refname:short) %(creatordate:unix)", "refs/tags").splitlines():
        tag, _, stamp = line.partition(" ")
        if STABLE_RE.match(tag) and stamp.strip().isdigit():
            dates[tag] = int(stamp)
    return dates


def infer(project, factory, onboarded, warn):
    """The answers for a project without an answers file, from its files and history (criteria 9 and 10)."""
    project = Path(project)
    name = project.resolve().name
    template = ("typescript" if (project / "package.json").is_file()
                else "python" if (project / "pyproject.toml").is_file() else "generic")
    origin = git(project, "remote", "get-url", "origin", check=False)
    m = REMOTE_RE.search(origin.stdout.strip()) if origin.returncode == 0 else None
    owner = m.group(1) if m else ""
    ci = project / ".github" / "workflows" / "ci.yml"
    uses = USES_RE.search(ci.read_text(encoding="utf-8", errors="replace")) if ci.is_file() else None
    factory_origin = git(factory, "remote", "get-url", "origin", check=False)
    fm = REMOTE_RE.search(factory_origin.stdout.strip()) if factory_origin.returncode == 0 else None
    src = uses.group(1) if uses else (f"{fm.group(1)}/{fm.group(2)}" if fm else "YOUR_ORG/software-factory")
    year, version = str(time.localtime().tm_year), None
    tags = tag_dates(factory)
    if onboarded:
        version = newest(factory)
    else:
        log = git(project, "log", "--format=%H %at", f"--grep=^{SCAFFOLD_SUBJECT}", check=False)
        found = log.stdout.split("\n") if log.returncode == 0 else []
        found = [line.split() for line in found if line.strip()]
        if found:
            stamp = int(found[-1][1])   # the oldest one: the first commit
            year = str(time.localtime(stamp).tm_year)
            # The newest release made at or before the scaffold: a base too new would make the merge keep the
            # project's old lines silently; one too old only gives extra conflicts.
            before = {t: v for t, v in stable_tags(factory).items() if tags.get(t, stamp + 1) <= stamp}
            version = max(before, key=before.get) if before else None
            if version is None:
                warn("no factory release is older than the project's scaffold commit: set the base with "
                     "--set version=<tag>")
        else:
            tagged = stable_tags(factory)
            version = min(tagged, key=tagged.get) if tagged else None
            warn(f"no '{SCAFFOLD_SUBJECT}' commit found: assumed the oldest release ({version}) as the base, which "
                 "gives more conflicts but never hides a change; correct it with --set version=<tag>")
    if version is None and onboarded:
        warn("the factory has no release tag (git fetch --tags in the factory)")
    return {"_src_path": src, "_commit": (commit_of(factory, version) if version else None) or UNKNOWN,
            "version": version or UNKNOWN, "template": template, "project_name": name,
            "package_name": name.replace("-", "_"), "github_owner": owner, "year": year, "onboarded": onboarded,
            "skip": []}


def apply_sets(answers, sets, factory):
    for item in sets:
        key, sep, value = item.partition("=")
        if not sep or key not in ANSWER_KEYS:
            raise Usage(f"--set {item}: expected key=value with key one of {', '.join(ANSWER_KEYS)}")
        if key == "skip":
            answers[key] = [v.strip() for v in value.split(",") if v.strip()]
        elif key == "onboarded":
            if value not in ("true", "false"):
                raise Usage("--set onboarded= takes true or false")
            answers[key] = value == "true"
        else:
            answers[key] = value
            if key == "version":
                answers["_commit"] = commit_of(factory, value) or UNKNOWN
    return answers


def onboard(project, factory, answers, out):
    """Write what an onboarded project takes from the factory now (criterion 10); returns the files it lacks (skip)."""
    target, _, _ = render(factory, answers["version"], answers)
    rules = rules_at(factory, answers["_commit"]) or []
    writes, skip, look = {}, [], []
    for rel, data in sorted(target.items()):
        if rel == ANSWERS:
            continue
        kind, mine = kind_of(rel, rules), read(project, rel)
        if kind == "managed":
            if mine is not None and lf(mine) != data:
                diff = difflib.unified_diff(lf(mine).decode("utf-8", "replace").splitlines(),
                                            data.decode("utf-8", "replace").splitlines(),
                                            f"{rel} (project)", f"{rel} (factory)", lineterm="")
                out("\n".join(diff))
            if mine is None or lf(mine) != data:
                writes[rel] = data
        elif mine is None:
            skip.append(rel)
        elif kind == "seeded":
            block = block_of(data, rel)
            if block:
                new = with_block(utf8(mine, rel), block, rel).encode("utf-8")
                if new != lf(mine):
                    writes[rel] = new
        elif lf(mine) != data:
            look.append(rel)
    apply(project, writes, [], rules)
    if writes:
        out("Written: " + ", ".join(writes))
    if look:
        out("Differ from the factory's version (not changed; compare them by hand): " + ", ".join(look))
    return skip


def adopt(project, factory, onboarded, sets, yes, out=print):
    if (Path(project) / ANSWERS).exists():
        raise Usage(f"{ANSWERS} already exists: this project is adopted (run update instead)")
    warnings = []
    answers = apply_sets(infer(project, factory, onboarded, warnings.append), sets, factory)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    check_answers(answers, "the inferred answers")
    out("Inferred answers (correct any of them with --set key=value):")
    out(dump_answers(answers).rstrip("\n"))
    if not yes:
        out("Nothing written. Check every answer with the user, then run again with --yes (and any --set).")
        return 0
    if answers["version"] == UNKNOWN or answers["_commit"] == UNKNOWN:
        raise Usage("the base version is unknown: set it with --set version=<tag> (git fetch --tags in the factory)")
    if onboarded:
        clean_tree(project)
        answers["skip"] = sorted(set(answers["skip"]) | set(onboard(project, factory, answers, out)))
    path = inside(project, ANSWERS)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dump_answers(answers).encode("utf-8"))
    out(f"Wrote {ANSWERS}.")
    return 0


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    commands = {name: sub.add_parser(name) for name in ("render", "update", "check", "adopt")}
    for name, c in commands.items():
        c.add_argument("--factory", default=str(ROOT))
        if name != "render":
            c.add_argument("--project", default=".")
    commands["render"].add_argument("--ref", required=True)
    commands["render"].add_argument("--answers", required=True)
    commands["render"].add_argument("--out", required=True)
    commands["update"].add_argument("--to")
    commands["adopt"].add_argument("--onboarded", action="store_true")
    commands["adopt"].add_argument("--set", action="append", default=[], dest="sets")
    commands["adopt"].add_argument("--yes", action="store_true")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if a.command == "render":
            answers = check_answers(parse_answers(Path(a.answers).read_text(encoding="utf-8"), a.answers), a.answers)
            files, _, version = render(a.factory, a.ref, answers)
            write_out(files, a.out)
            print(f"Rendered {answers['template']} at {version} into {a.out} ({len(files)} files)")
            return 0
        if a.command == "update":
            return update(a.project, a.factory, a.to)
        if a.command == "check":
            return check(a.project, a.factory)
        return adopt(a.project, a.factory, a.onboarded, a.sets, a.yes)
    except Usage as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    except OSError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
