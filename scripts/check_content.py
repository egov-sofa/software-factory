#!/usr/bin/env python3
"""Look for content that must not be in this repository: secrets (private keys, cloud and API tokens), public IP
addresses, internal host names, and terms from a denylist that is never committed (customer and employer names,
internal system names).

Shared service of the software factory (docs/SHARED-SERVICES.md). Projects get a copy in scripts/ for the local
hooks; CI runs the factory's own copy at the pinned tag through the content-guard action. Adapted from
egov-ai/claude-skills.

What is checked:
  --diff BASE        lines added since BASE (git diff BASE...HEAD), and the messages of the commits in BASE..HEAD
  --staged           lines added in the staged changes (used by the pre-commit hook)
  --all              every line of every tracked text file
  --text-env NAME    the text in environment variable NAME (for a pull request title and description); repeatable
  --text-file PATH   the text in file PATH (used by the commit-msg hook)
  --root DIR         the repository to check (default: the one this script sits in); CI runs the base branch's
                     copy from outside the checkout, so nothing in the pull request can shadow its imports

File names are checked too. Public IP addresses are IPv4 and IPv6. Secrets are recognized by their fixed formats
(see SECRET_RULES), so a finding names the kind of secret, never its value.

The denylist is read from the file .content-denylist at the repository root (git-ignored) and from the environment
variable CONTENT_DENYLIST (a CI secret). One term per line, case-insensitive, matched as a whole word; lines starting
with # are comments. The words of a term match across any whitespace, also when a line wrap splits them.

A line that holds an intended example can end with the marker  content-ok  to skip the built-in rules (never the
denylist). A line with a denylisted term reports only that term's number: the other rules would print the value.

Exit code 0 if nothing is found, 1 if something is found, 2 on a usage error.
"""
import ipaddress
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DENYLIST_FILE = ROOT / ".content-denylist"
MARKER = "content-ok"

IPV4_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?:/\d{1,2})?(?!\d|\.\d)")   # a final full stop is fine
# loose IPv6 candidates; ipaddress decides what is a valid address
IPV6_RE = re.compile(r"(?<![\w:.])((?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4})(?:/\d{1,3})?(?![\w:])", re.I)
INTERNAL_TLDS = ("local", "corp", "internal", "lan", "intranet", "intra", "localdomain")
# the suffix must end the name: settings.local.json and mail.corp.contoso.com are not internal hosts
HOST_RE = re.compile(r"\b((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:" + "|".join(INTERNAL_TLDS) + r"))"
                     r"(?![\w-]|\.[\w-])", re.I)
PLACEHOLDER_LABELS = {"example", "contoso", "fabrikam"}   # documentation names, never real hosts
CODE_OBJECTS = {"self", "this", "cls"}   # self.internal, this.local: attributes in code, not hosts
# a four-part number right after "version" or "v" is a version (.NET assembly, Windows file), not an address
VERSION_BEFORE_RE = re.compile(r"(?i)(?:\bversion\b[\s=:\"']*|\bv)$")
# a .NET namespace (Microsoft.Extensions.Internal): a PascalCase suffix after two or more PascalCase identifiers;  # content-ok
# a capitalised host name in prose (Fileserver.corp, Sql01.corp.local) is still a host  # content-ok
PASCAL_SUFFIX_RE = re.compile(r"[A-Z][a-z]+")
PASCAL_ID_RE = re.compile(r"[A-Z][A-Za-z]*[a-z][A-Za-z]*")


# High-confidence formats only: each one has a fixed prefix, so ordinary code and prose do not match.
SECRET_RULES = [
    ("private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("AWS access key ID", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])")),
    ("GitHub token", re.compile(r"(?<!\w)(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})")),
    ("Anthropic API key", re.compile(r"(?<!\w)sk-ant-[A-Za-z0-9_-]{20,}")),
    ("Slack token", re.compile(r"(?<!\w)xox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"(?<!\w)AIza[0-9A-Za-z_-]{35}(?![\w-])")),
    ("Stripe live key", re.compile(r"(?<!\w)[rs]k_live_[0-9A-Za-z]{20,}")),
]


def denylist():
    terms = {}   # lower-cased term -> term; matching ignores case, so duplicates do too (the first one is kept)
    # utf-8-sig: Notepad may save the file with a BOM, which would stick to the first term
    sources = [DENYLIST_FILE.read_text(encoding="utf-8-sig")] if DENYLIST_FILE.is_file() else []
    sources.append(os.environ.get("CONTENT_DENYLIST", ""))
    for text in sources:
        for t in (line.strip() for line in text.splitlines()):
            if t and not t.startswith("#"):
                terms.setdefault(t.lower(), t)
    # the words of a term match across any whitespace: "Big  Corp", or "Big" and "Corp" on two lines joined by wrapped()
    return [re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, t.split())) + r"(?!\w)", re.I) for t in terms.values()]


def wrapped(prev, line, deny):
    """Denylist terms that only appear when two consecutive lines are joined: a line wrap split the term."""
    joined = f"{prev} {line}"
    return [f"denylist term {n} (split across this line and the next)" for n, p in enumerate(deny, 1)
            if p.search(joined) and not p.search(prev) and not p.search(line)]


NAMESPACE_BEFORE_RE = re.compile(r"\b(?:using|namespace|import)\s+(?:static\s+)?$")


def _namespace(name, before, after):
    """A .NET namespace: a PascalCase suffix after two or more PascalCase identifiers, written as code (after using,
    namespace or import, or followed by ; ( < or a dot and an identifier). The same shape in prose is a host, also at the
    end of a sentence (Fileserver.Paris.Corp.)."""  # content-ok
    labels = name.split(".")
    shape = (bool(PASCAL_SUFFIX_RE.fullmatch(labels[-1]))
             and sum(1 for label in labels[:-1] if PASCAL_ID_RE.fullmatch(label)) >= 2)
    return shape and (bool(NAMESPACE_BEFORE_RE.search(before)) or after[:1] in (";", "(", "<")
                                                                 or bool(re.match(r"\.[A-Za-z_]", after)))


def ipv6_like(text):
    """An IPv6 candidate worth checking. Public addresses start with a group from 2000 to 3fff, four hex digits;
    that rules out slices such as argv[::2] or s[1::3]. A digit is required too: Face::Face() and Add::add are hex
    words in code."""
    return bool(re.match(r"[0-9a-f]{4}:", text, re.I)) and bool(re.search(r"\d", text))


def findings(line, deny):
    """The problems in one line of text, as short descriptions; denylist terms are never quoted back."""
    found = [f"denylist term {n}" for n, p in enumerate(deny, 1) if p.search(line)]
    if found:
        return found   # an IP or host finding would print its value, which can contain the term
    if line.rstrip().endswith(MARKER):
        return found
    found += [f"possible secret ({kind})" for kind, pattern in SECRET_RULES if pattern.search(line)]
    for m in (*IPV4_RE.finditer(line), *(m for m in IPV6_RE.finditer(line) if ipv6_like(m.group(1)))):
        try:
            ip = ipaddress.ip_address(m.group(1))
        except ValueError:
            continue
        if ip.is_global and not VERSION_BEFORE_RE.search(line[:m.start()]):
            found.append(f"public IP address {m.group(0)}")
    for m in HOST_RE.finditer(line):
        name = m.group(1)
        labels = name.lower().split(".")
        if PLACEHOLDER_LABELS & set(labels) or labels[0] in CODE_OBJECTS or line[m.end():m.end() + 1] == "(":
            continue   # a documentation name, an attribute (self.internal) or a call (threading.local())
        if ((line[m.start() - 1:m.start()] == "." and labels[0] == "env")
                or _namespace(name, line[:m.start()], line[m.end():])):
            continue   # a dotenv file name (.env.local, .env.production.local) or a .NET namespace
        found.append(f"internal host name {name}")
    return found


def git(*args):
    # quotePath=false: git otherwise writes non-ASCII file names as quoted octal escapes
    return subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def unquote(path):
    """A path as git prints it in a diff header; names with quotes, tabs or newlines stay C-quoted."""
    if path.startswith('"') and path.endswith('"'):
        # UTF-8 first: with quotePath=false, non-ASCII characters arrive decoded; the escapes themselves are ASCII
        path = path[1:-1].encode("utf-8").decode("unicode_escape").encode("latin-1").decode(
            "utf-8", "replace")
    return path


def added_lines(diff_args):
    """(path, line number, text) for every added line of a git diff, binary content included.

    --text: the pull request controls .gitattributes, and "* -diff" or "* binary" would otherwise make git hide
    every added line as "Binary files differ". Nothing is skipped as binary either, since a NUL byte would then hide
    the rest of a line or file: NUL bytes become spaces and every line is checked. Random bytes in an image rarely
    form an address or an internal domain; when they do, the finding names the file.
    The hunk header gives the number of added lines, so an added line that itself starts with '++ ' is content,
    not a file header."""
    path, num, left = None, 0, 0
    # fixed prefixes: diff.mnemonicPrefix and diff.noprefix would otherwise change the +++ b/ headers
    for line in git("diff", "--unified=0", "--no-color", "--no-ext-diff", "--text", "--src-prefix=a/",
                    "--dst-prefix=b/", *diff_args).split("\n"):
        if left and line.startswith("+"):
            if path:
                yield path, num, line[1:].replace(chr(0), " ")
            num += 1
            left -= 1
        elif line.startswith("@@"):
            m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
            num, left = int(m.group(1)), int(m.group(2) or 1)
        elif line.startswith("+++ "):
            name = unquote(line[4:])
            path = name[2:] if name.startswith("b/") else None
    # file names come from their own list: renames, binary files and empty new files have no +++ header
    for name in git("diff", "--name-only", "-z", "--no-renames", "--diff-filter=d", *diff_args).split("\0"):
        if name:
            yield name, 0, name


def commit_lines(base):
    """(commit, line number, text) for the messages of the commits in base..HEAD."""
    for entry in git("log", "--format=%h%n%B%x00", f"{base}..HEAD").split("\0"):
        sha, _, message = entry.strip().partition("\n")
        for num, line in enumerate(message.splitlines(), 1):
            yield f"commit {sha}", num, line


def env_lines(name):
    for num, line in enumerate(os.environ.get(name, "").splitlines(), 1):
        yield name, num, line


def file_lines(path):
    """The lines of a commit message file. The commit-msg hook gets the file before git cleans it up, so the
    `git commit -v` diff below the scissors line (removed content) is skipped. Comment lines are kept but marked:
    git drops them only when an editor was used, while `-m` and `-F` keep a line such as '#24 ...'. They are checked
    against the denylist only, since git's own comments list file names that may be removed content."""
    try:
        comment = git("config", "--get", "core.commentChar").strip() or "#"
    except subprocess.CalledProcessError:
        comment = "#"
    if comment == "auto":
        comment = "#"
    where = "commit message" if Path(path).name == "COMMIT_EDITMSG" else path
    for num, line in enumerate(Path(path).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if line.startswith(comment) and ">8" in line and line.strip(comment + " ->8") == "":
            break   # the scissors line: git drops it and everything below
        # the marker limits a comment line to the denylist, as for an intended example
        yield where, num, f"{line}  {MARKER}" if line.startswith(comment) else line


def tracked_lines():
    for rel in git("ls-files", "-z").split("\0"):
        if not rel:
            continue
        yield rel, 0, rel   # the file name is content too
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue   # binary or unreadable
        for num, line in enumerate(text.splitlines(), 1):
            yield rel, num, line


def main(argv):
    global ROOT, DENYLIST_FILE
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            print(__doc__, file=sys.stderr)
            return 2
        ROOT = Path(argv[i + 1]).resolve()
        DENYLIST_FILE = ROOT / ".content-denylist"
        argv = argv[:i] + argv[i + 2:]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # non-ASCII file names on a Windows console
    sources, deny = [], denylist()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--staged":
            sources.append(("staged changes", added_lines(["--cached"])))
        elif a == "--all":
            sources.append(("tracked files", tracked_lines()))
        elif a in ("--diff", "--text-env", "--text-file") and i + 1 < len(argv):
            i += 1
            if a == "--diff":
                sources.append((f"changes since {argv[i]}", added_lines([f"{argv[i]}...HEAD"])))
                sources.append(("commit messages", commit_lines(argv[i])))
            elif a == "--text-env":
                sources.append((argv[i], env_lines(argv[i])))
            else:
                sources.append(("the message", file_lines(argv[i])))
        else:
            print(__doc__, file=sys.stderr)
            return 2
        i += 1
    if not sources:
        print(__doc__, file=sys.stderr)
        return 2

    problems = 0
    for _label, lines in sources:
        prev = None   # (where, num, line) of the line before, to catch a term split by a line wrap
        for where, num, line in lines:
            if any(p.search(where) for p in deny):
                where = "(a file whose path holds a denylist term)"   # never print the term as a location
            if prev and prev[0] == where and num == prev[1] + 1 and num > 1:
                for f in wrapped(prev[2], line, deny):
                    print(f"{where}:{prev[1]}: {f}")
                    problems += 1
            for f in findings(line, deny):
                print(f"{where}: file name: {f}" if num == 0 else f"{where}:{num}: {f}")
                problems += 1
            prev = (where, num, line)
    names = ", ".join(label for label, _ in sources)
    if problems:
        print(f"\n{problems} problem(s) in {names}. Remove the content, or end an intended example line with "
              f"'{MARKER}' (built-in rules only).")
        return 1
    print(f"No problems in {names} ({len(deny)} denylist term(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
