#!/usr/bin/env python3
import curses
import os
import stat
import pwd
import grp
import time
import subprocess
import re
import shutil
import textwrap
from git import Repo
from git.exc import InvalidGitRepositoryError
import sys

_cached_path = None
_cached_branch = None
_clipboard = {
    "path": None,
    "cut": False,
}


def copy_entity(stdscr, current_path, entries, selected):
    name = entries[selected]
    full = os.path.join(current_path, name)
    _clipboard["path"] = full
    _clipboard["cut"] = False
    _show_status(stdscr, f"Copied: {name}")


def cut_entity(stdscr, current_path, entries, selected):
    name = entries[selected]
    full = os.path.join(current_path, name)
    _clipboard["path"] = full
    _clipboard["cut"] = True
    _show_status(stdscr, f"Cut: {name}")


def paste_entity(stdscr, current_path):
    src = _clipboard.get("path")
    if not src:
        _show_status(stdscr, "Clipboard is empty.")
        return

    base = os.path.basename(src.rstrip(os.sep))
    name, ext = os.path.splitext(base)

    if _clipboard["cut"]:
        paste_name = base
    else:
        paste_name = f"{name}-copy{ext}"

    dest = os.path.join(current_path, paste_name)

    try:
        if _clipboard["cut"]:
            shutil.move(src, dest)
            msg = f"Moved: {paste_name} -> {current_path}"
        else:
            if os.path.isdir(src):
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            msg = f"Copied: {paste_name} into {current_path}"

        if _clipboard["cut"]:
            _clipboard["path"] = None
            _clipboard["cut"] = False

        _show_status(stdscr, msg)

    except Exception as e:
        _show_error_curses(stdscr, f"Error while pasting: {e}")


def _show_status(stdscr, message, duration=1.5):
    h, w = stdscr.getmaxyx()
    stdscr.attron(curses.A_BOLD)
    stdscr.addstr(h - 1, 0, message[: w - 1].ljust(w - 1))
    stdscr.attroff(curses.A_BOLD)
    stdscr.refresh()
    time.sleep(duration)
    stdscr.addstr(h - 1, 0, " " * (w - 1))
    stdscr.refresh()


def prompt_string(stdscr, title, prompt_text):
    curses.noecho()
    h, w = stdscr.getmaxyx()
    box_width = max(len(prompt_text), len(title)) + 50
    win = curses.newwin(3, box_width, h // 2 - 1, (w - box_width) // 2)
    win.bkgd(" ", curses.color_pair(5))
    win.box()
    win.addstr(0, 2, f" {title} ", curses.A_BOLD)
    win.addstr(1, 2, prompt_text)
    win.refresh()
    curses.curs_set(1)
    input_win = curses.newwin(
        1,
        box_width - len(prompt_text) - 4,
        h // 2,
        (w - box_width) // 2 + len(prompt_text) + 2,
    )
    buffer = ""
    while True:
        ch = input_win.getch()
        if ch in (10, 13):  # Enter
            break
        if ch == 27:  # ESC
            buffer = None
            break
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if buffer:
                buffer = buffer[:-1]
                y, x = input_win.getyx()
                input_win.delch(y, x - 1)
        else:
            try:
                c = chr(ch)
                if c.isprintable():
                    buffer += c
                    input_win.addstr(c)
            except:
                pass
    curses.curs_set(0)
    win.clear()
    win.refresh()
    return buffer


def create_entity(stdscr, current_path):
    name = prompt_string(stdscr, "Create", "Name: ")
    if name is None:
        return None
    full = os.path.join(current_path, name)
    try:
        if os.path.splitext(name)[1]:
            open(full, "w").close()
        else:
            os.mkdir(full)
        return name
    except Exception as e:
        _show_error_curses(stdscr, f"Error: {e}")
        return None


def rename_entity(stdscr, current_path, entries, selected):
    old = entries[selected]
    new = prompt_string(stdscr, "Rename", f"Rename '{old}' to: ")
    if new is None:
        return None
    full_old = os.path.join(current_path, old)
    full_new = os.path.join(current_path, new)
    try:
        os.rename(full_old, full_new)
        return new
    except Exception as e:
        _show_error_curses(stdscr, f"Error: {e}")
        return None


def delete_entity(stdscr, current_path, entries, selected):
    name = entries[selected]
    confirm = prompt_string(stdscr, "Delete", f"Delete '{name}'? [y/N]: ")
    if confirm is None or not confirm.lower().startswith("y"):
        return
    full = os.path.join(current_path, name)
    try:
        if os.path.isdir(full) and not os.path.islink(full):
            shutil.rmtree(full)
        else:
            os.remove(full)
    except Exception as e:
        _show_error_curses(stdscr, f"Error deleting '{name}': {e}")


def get_branch_for_path(path):
    global _cached_path, _cached_branch

    if path != _cached_path:
        _cached_path = path
        try:
            repo = Repo(path, search_parent_directories=True)
            _cached_branch = repo.active_branch.name
        except (InvalidGitRepositoryError, TypeError):
            _cached_branch = None

    return _cached_branch


def update_selection_from_regex(buffer, entries):
    if buffer.startswith("/") and len(buffer) > 1:
        try:
            pattern = re.compile(buffer[1:], re.IGNORECASE)
            for idx, name in enumerate(entries):
                if name not in ("..", ".") and pattern.search(name):
                    return idx
        except re.error:
            pass
    return None


def show_output_curses(stdscr, output_text, title="Output"):
    h, w = stdscr.getmaxyx()
    win_h = int(h * 0.8)
    win_w = int(w * 0.8)
    win_y = (h - win_h) // 2
    win_x = (w - win_w) // 2

    win = curses.newwin(win_h, win_w, win_y, win_x)
    win.bkgd(" ", curses.color_pair(5))
    win.box()

    title_str = f" {title} "
    win.addstr(0, 2, title_str, curses.A_BOLD)

    lines = output_text.splitlines()
    max_lines = win_h - 4
    offset = 0

    while True:
        win.erase()
        win.box()
        win.addstr(0, 2, title_str, curses.A_BOLD)

        section = None
        line_index = 0
        for idx in range(offset, min(offset + max_lines, len(lines))):
            raw = lines[idx]

            if raw.startswith("Changes to be committed"):
                section = "staged"
                win.addstr(1 + line_index, 2, raw[: win_w - 4], curses.A_DIM)
                line_index += 1
                continue
            elif raw.startswith("Changes not staged for commit"):
                section = "unstaged"
                win.addstr(1 + line_index, 2, raw[: win_w - 4], curses.A_DIM)
                line_index += 1
                continue
            elif raw.strip().startswith("(use ") and (
                section in ("staged", "unstaged")
            ):
                win.addstr(1 + line_index, 2, raw[: win_w - 4], curses.A_DIM)
                line_index += 1
                continue

            hunk = re.search(r"\s*@@.*?@@", raw)
            if hunk:
                y = 1 + line_index
                x = 2
                start, end = hunk.span()
                pre = raw[:start]
                mid = raw[start:end]
                post = raw[end : win_w - 4]

                win.addstr(y, x, pre)
                x += len(pre)

                win.addstr(y, x, mid, curses.color_pair(1))
                x += len(mid)

                win.addstr(y, x, post)
                line_index += 1
                continue

            elif raw.startswith("+++ ") or raw.startswith("--- "):
                color = curses.A_BOLD
            elif raw.startswith("+"):
                color = curses.color_pair(6)
            elif raw.startswith("-") and not raw.startswith("--- "):
                color = curses.color_pair(3)
            else:
                if section == "staged":
                    color = curses.color_pair(6)
                elif section == "unstaged":
                    color = curses.color_pair(3)
                else:
                    color = curses.A_BOLD

            win.addstr(1 + line_index, 2, raw[: win_w - 4], color)
            line_index += 1

        footer = "<Click Q to exit>"
        win.addstr(win_h - 2, 2, footer[: win_w - 4], curses.A_DIM)
        win.refresh()

        key = win.getch()
        if key == ord("q"):
            break
        elif key == curses.KEY_DOWN or key == ord("j"):
            if offset + max_lines < len(lines):
                offset += 1
        elif key == curses.KEY_UP or key == ord("k"):
            if offset > 0:
                offset -= 1
        elif key == curses.KEY_NPAGE:
            offset = min(offset + max_lines, len(lines) - max_lines)
        elif key == curses.KEY_PPAGE:
            offset = max(offset - max_lines, 0)
        elif key == ord("g"):
            offset = 0
        elif key == ord("G"):
            offset = max(len(lines) - max_lines, 0)

    win.erase()
    win.refresh()
    del win
    stdscr.clear()
    stdscr.refresh()


def format_mode(mode):
    is_dir = "d" if stat.S_ISDIR(mode) else "-"
    perms = ""
    for who in ("USR", "GRP", "OTH"):
        for what in ("R", "W", "X"):
            flag = getattr(stat, f"S_I{what}{who}")
            perms += what.lower() if (mode & flag) else "-"
    return is_dir + perms


def format_time(epoch_seconds):
    lt = time.localtime(epoch_seconds)
    now = time.localtime()
    if lt.tm_year != now.tm_year:
        return time.strftime("%b %e  %Y", lt)
    else:
        return time.strftime("%b %e %H:%M", lt)


def human_readable(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes}B"
    for unit in ("K", "M", "G", "T"):
        size_bytes /= 1024.0
        if size_bytes < 1024:
            if size_bytes < 10:
                return f"{size_bytes:.1f}{unit}"
            else:
                return f"{size_bytes:.0f}{unit}"
    size_bytes /= 1024.0
    return f"{size_bytes:.0f}P"


def _show_error_curses(stdscr, message):
    h, w = stdscr.getmaxyx()

    raw_lines = message.split("\n")
    wrapped = []
    max_msg_w = w - 6
    for ln in raw_lines:
        wrapped.extend(textwrap.wrap(ln, max_msg_w) or [""])
    lines = wrapped

    box_w = min(max(len(l) for l in lines) + 4, w)
    box_h = min(len(lines) + 4, h)
    box_y = max((h - box_h) // 2, 0)
    box_x = max((w - box_w) // 2, 0)

    win = curses.newwin(box_h, box_w, box_y, box_x)
    win.bkgd(" ", curses.color_pair(3) | curses.A_BOLD)
    win.box()
    for idx, line in enumerate(lines):
        win.addstr(1 + idx, 2, line[: box_w - 4])
    prompt = "<Press any key>"
    win.addstr(box_h - 2, box_w - len(prompt) - 2, prompt)
    win.refresh()
    win.getch()
    win.clear()
    win.refresh()
    del win
    stdscr.clear()
    stdscr.refresh()


def execute_command(stdscr, cmd, current_path):
    parts = [p.strip() for p in cmd.split(";") if p.strip()]
    global _cached_path, _cached_branch
    new_path = current_path

    for part in parts:
        if part.startswith("git checkout"):
            _cached_path = None
            _cached_branch = None
        if part == "cd" or part.startswith("cd "):
            if part == "cd":
                target = os.path.expanduser("~")
            else:
                target = part[3:].strip()
                target = os.path.expanduser(target)

            if not os.path.isabs(target):
                candidate = os.path.normpath(os.path.join(new_path, target))
            else:
                candidate = target

            if os.path.isdir(candidate):
                new_path = candidate
            else:
                msg = (
                    f"Cannot enter '{candidate}': does not exist or is not a directory."
                )
                curses.flash()
                _show_error_curses(stdscr, msg)
        else:
            try:
                env_override = os.environ.copy()
                env_override["GIT_PAGER"] = "cat"
                proc = subprocess.Popen(
                    part,
                    shell=True,
                    cwd=new_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                out, err = proc.communicate()
                full_output = ""
                if out:
                    full_output += out
                if err:
                    full_output += ("\n" if full_output else "") + err
                if proc.returncode != 0:
                    full_output += f"\n\n(Return code: {proc.returncode})"

                if full_output.strip():
                    show_output_curses(stdscr, full_output, title=part)
            except Exception as e:
                msg = f"Error while executing '{part}': {e}"
                curses.flash()
                _show_error_curses(stdscr, msg)

    return new_path


def find_autocomplete_suggestion(buffer, current_path):
    assert buffer.startswith("cd ")
    raw = buffer[3:]
    basedir, partial = os.path.split(raw)

    if os.path.isabs(basedir):
        search_dir = basedir
    else:
        search_dir = os.path.normpath(os.path.join(current_path, basedir))

    try:
        entries = os.listdir(search_dir)
    except Exception:
        return raw, "", False

    candidates = [e for e in entries if e.startswith(partial)]
    if not candidates:
        return raw, "", False

    if len(candidates) == 1:
        single = candidates[0]
        rest = single[len(partial) :]
        fullpath = os.path.join(search_dir, single)
        if os.path.isdir(fullpath):
            rest += "/"
        return raw, rest, os.path.isdir(fullpath)

    common = os.path.commonprefix(candidates)
    rest = common[len(partial) :]
    return raw, rest, False


def draw_directory(stdscr, current_path, selected, command_mode=False, cmd_buffer=""):
    raw = os.listdir(current_path)
    entries = [".."] + sorted(raw)

    metadata = {}
    for name in entries:
        full = os.path.join(current_path, name)
        try:
            st = os.lstat(full)
        except OSError:
            metadata[name] = ("?" * 10, "?", "?", "?", "?", "?")
            continue

        mode_str = format_mode(st.st_mode)
        nlink = st.st_nlink
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner = str(st.st_uid)
        try:
            group = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            group = str(st.st_gid)

        size_hr = human_readable(st.st_size)
        mtime_str = format_time(st.st_mtime)
        metadata[name] = (mode_str, nlink, owner, group, size_hr, mtime_str)

    h, w = stdscr.getmaxyx()
    reserved_lines = 2 if command_mode else 0
    max_display = (h - 2) - reserved_lines
    total = len(entries)

    if total <= max_display:
        offset = 0
    else:
        if selected < max_display:
            offset = 0
        else:
            offset = selected - (max_display - 1)
        if offset > total - max_display:
            offset = total - max_display

    stdscr.erase()
    header = f" {current_path}"
    stdscr.addstr(0, 0, header[: w - 1], curses.A_REVERSE)
    stdscr.addstr(1, 0, "-" * (w - 1))

    for idx in range(offset, min(offset + max_display, total)):
        name = entries[idx]
        mode_str, nlink, owner, group, size_hr, mtime_str = metadata[name]
        full = os.path.join(current_path, name)
        display_name = name + ("/" if os.path.isdir(full) else "")
        screen_y = (idx - offset) + 2

        part_mode = f"{mode_str}"
        part_nlink = f"{nlink:>3}"
        part_owner = f"{owner:<8}"
        part_group = f"{group:<8}"
        part_size = f"{size_hr:>8}"
        part_time = f"{mtime_str:>12}"
        part_name = f" {display_name}"
        prefix = f"{part_mode} {part_nlink} {part_owner} {part_group} {part_size} {part_time}"

        if idx == selected:
            attr_prefix = curses.A_REVERSE
            if os.path.isdir(full):
                attr_name = curses.color_pair(1) | curses.A_REVERSE
            else:
                attr_name = curses.color_pair(2) | curses.A_REVERSE
        else:
            attr_prefix = curses.A_NORMAL
            if os.path.isdir(full):
                attr_name = curses.color_pair(1)
            else:
                attr_name = curses.color_pair(2)

        max_width = w - 1
        stdscr.addstr(screen_y, 0, prefix[:max_width], attr_prefix)
        prefix_len = min(len(prefix), max_width)
        if prefix_len < max_width:
            remaining = max_width - prefix_len
            stdscr.addstr(screen_y, prefix_len, part_name[:remaining], attr_name)

    if command_mode:
        branch = get_branch_for_path(current_path)
        if branch:
            branch_line = f"Branch: {branch}"
            stdscr.move(h - 3, 0)
            stdscr.clrtoeol()
            stdscr.addstr(h - 3, 0, branch_line.ljust(w - 1), curses.A_BOLD)
        pwd_line = f"PWD: {current_path}"
        stdscr.addstr(h - 2, 0, pwd_line[: w - 1])

        if cmd_buffer.startswith("cd "):
            raw = cmd_buffer[3:]
            _, suggestion, _ = find_autocomplete_suggestion(cmd_buffer, current_path)

            base = "Cmd: cd " + raw
            stdscr.addstr(h - 1, 0, base[: w - 1], curses.color_pair(5))

            if len(suggestion) > 0 and len(base) < w - 1:
                max_sug = min(len(suggestion), (w - 1) - len(base))
                stdscr.addstr(h - 1, len(base), suggestion[:max_sug], curses.A_BOLD)
        else:
            prompt = f"Cmd: {cmd_buffer}"
            stdscr.addstr(h - 1, 0, prompt[: w - 1], curses.color_pair(5))

        stdscr.move(h - 1, min(len("Cmd: ") + len(cmd_buffer), w - 1))

    stdscr.refresh()
    return entries


def draw_directory_and_preview(
    stdscr, current_path, selected, command_mode=False, cmd_buffer=""
):
    raw = os.listdir(current_path)
    entries = [".."] + sorted(raw)

    metadata = {}
    for name in entries:
        full = os.path.join(current_path, name)
        try:
            st = os.lstat(full)
        except OSError:
            metadata[name] = ("?" * 10, "?", "?", "?", "?", "?")
            continue

        mode_str = format_mode(st.st_mode)
        nlink = st.st_nlink
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner = str(st.st_uid)
        try:
            group = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            group = str(st.st_gid)

        size_hr = human_readable(st.st_size)
        mtime_str = format_time(st.st_mtime)
        metadata[name] = (mode_str, nlink, owner, group, size_hr, mtime_str)

    h, w = stdscr.getmaxyx()
    left_width = int(w * 0.55)
    right_width = w - left_width - 1

    stdscr.erase()
    header = f" {current_path}"
    stdscr.addstr(0, 0, header[: left_width - 1], curses.A_REVERSE)
    stdscr.addstr(1, 0, "-" * (left_width - 1))
    for yy in range(h):
        stdscr.addstr(yy, left_width, "|", curses.A_DIM)

    total = len(entries)
    reserved_lines = 2 if command_mode else 0
    max_display = (h - 2) - reserved_lines
    if total <= max_display:
        offset = 0
    else:
        if selected < max_display:
            offset = 0
        else:
            offset = selected - (max_display - 1)
        if offset > total - max_display:
            offset = total - max_display

    for idx in range(offset, min(offset + max_display, total)):
        name = entries[idx]
        mode_str, nlink, owner, group, size_hr, mtime_str = metadata[name]
        full = os.path.join(current_path, name)
        display_name = name + ("/" if os.path.isdir(full) else "")
        screen_y = (idx - offset) + 2

        part_mode = f"{mode_str}"
        part_nlink = f"{nlink:>3}"
        part_owner = f"{owner:<8}"
        part_group = f"{group:<8}"
        part_size = f"{size_hr:>8}"
        part_time = f"{mtime_str:>12}"
        part_name = f" {display_name}"
        prefix = f"{part_mode} {part_nlink} {part_owner} {part_group} {part_size} {part_time}"

        if idx == selected:
            attr_prefix = curses.A_REVERSE
            if os.path.isdir(full):
                attr_name = curses.color_pair(1) | curses.A_REVERSE
            else:
                attr_name = curses.color_pair(2) | curses.A_REVERSE
        else:
            attr_prefix = curses.A_NORMAL
            if os.path.isdir(full):
                attr_name = curses.color_pair(1)
            else:
                attr_name = curses.color_pair(2)

        max_left = left_width - 1
        stdscr.addstr(screen_y, 0, prefix[:max_left], attr_prefix)
        prefix_len = min(len(prefix), max_left)
        if prefix_len < max_left:
            remaining = max_left - prefix_len
            stdscr.addstr(screen_y, prefix_len, part_name[:remaining], attr_name)

    if command_mode:
        pwd_line = f"PWD: {current_path}"
        stdscr.addstr(h - 2, 0, pwd_line[: left_width - 1])

        if cmd_buffer.startswith("cd "):
            prefix, suggestion, _ = find_autocomplete_suggestion(
                cmd_buffer, current_path
            )
            base = "Cmd: cd " + prefix
            stdscr.addstr(h - 1, 0, base[: left_width - 1], curses.A_NORMAL)
            if len(suggestion) > 0 and len(base) < left_width - 1:
                max_sug = min(len(suggestion), (left_width - 1) - len(base))
                stdscr.addstr(h - 1, len(base), suggestion[:max_sug], curses.A_REVERSE)
        else:
            prompt = f"Cmd: {cmd_buffer}"
            stdscr.addstr(h - 1, 0, prompt[: left_width - 1], curses.A_NORMAL)

        stdscr.move(h - 1, min(len("Cmd: ") + len(cmd_buffer), left_width - 1))

    draw_preview(
        stdscr, current_path, entries[selected], left_width + 1, right_width, h
    )

    stdscr.refresh()
    return entries


def draw_preview(stdscr, current_path, name, start_x, width, height):
    full = os.path.join(current_path, name)

    title = f" Preview: {name} "
    stdscr.addstr(0, start_x, title[: width - 1], curses.A_REVERSE)
    stdscr.addstr(1, start_x, "-" * (width - 1), curses.A_DIM)

    if os.path.isdir(full):
        try:
            entries = sorted(os.listdir(full))
            if not entries:
                stdscr.addstr(
                    2,
                    start_x,
                    "<Empty directory>".ljust(width - 1),
                    curses.color_pair(2),
                )
            else:
                for idx, e in enumerate(entries):
                    if idx >= height - 2:
                        break
                    disp = e + ("/" if os.path.isdir(os.path.join(full, e)) else "")
                    truncated = disp[: width - 1]
                    attr = (
                        curses.color_pair(1)
                        if os.path.isdir(os.path.join(full, e))
                        else curses.color_pair(2)
                    )
                    stdscr.addstr(2 + idx, start_x, truncated.ljust(width - 1), attr)
        except Exception as e:
            msg = f"<Error reading directory: {e}>"
            stdscr.addstr(
                2, start_x, msg[: width - 1], curses.color_pair(3) | curses.A_BOLD
            )
    else:
        lines = []
        try:
            with open(full, "r", encoding="utf-8") as f:
                for i in range(height - 3):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line.rstrip("\n")[: width - 1])
                if not lines:
                    lines = ["<Empty file>"]
        except UnicodeDecodeError:
            lines = [
                "<Binary file or of unknown format>",
                "Cannot show in form of text.",
            ]
        except Exception as e:
            lines = [f"<Error while reading: {e}>"]

        for idx, txt in enumerate(lines[: height - 2]):
            stdscr.addstr(2 + idx, start_x, txt.ljust(width - 1), curses.color_pair(2))


def main(stdscr):
    stdscr.keypad(True)
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_WHITE, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_GREEN, -1)

    current_path = os.getcwd()
    selected = 0
    command_mode = False
    cmd_buffer = ""
    preview_mode = False
    last_search = None
    search_matches = []
    current_match_idx = -1

    while True:
        if preview_mode:
            entries = draw_directory_and_preview(
                stdscr, current_path, selected, command_mode, cmd_buffer
            )
        else:
            entries = draw_directory(
                stdscr, current_path, selected, command_mode, cmd_buffer
            )

        n = len(entries)

        if command_mode:
            key = stdscr.getch()

            if key in (curses.KEY_ENTER, 10, 13):
                if cmd_buffer.startswith("/"):
                    pattern = cmd_buffer[1:]
                    try:
                        regex = re.compile(pattern, re.IGNORECASE)
                        raw = os.listdir(current_path)
                        entries = [".."] + sorted(raw)
                        search_matches = [
                            idx
                            for idx, name in enumerate(entries)
                            if name not in ("..", ".") and regex.search(name)
                        ]
                        if search_matches:
                            last_search = pattern
                            current_match_idx = 0
                            selected = search_matches[0]
                        else:
                            last_search = None
                            _show_status(stdscr, "No matches", duration=1.0)
                    except re.error:
                        _show_status(stdscr, "Invalid regex", duration=1.0)
                else:
                    current_path = execute_command(stdscr, cmd_buffer, current_path)
                cmd_buffer = ""
                command_mode = False
                stdscr.clear()
                curses.curs_set(0)
                stdscr.clear()
                continue

            elif key == 27:  # ESC
                command_mode = False
                cmd_buffer = ""
                stdscr.clear()
                curses.curs_set(0)
                continue

            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if len(cmd_buffer) > 0:
                    cmd_buffer = cmd_buffer[:-1]
                    new_sel = update_selection_from_regex(cmd_buffer, entries)
                    if new_sel is not None:
                        selected = new_sel
                continue

            elif key == 9:
                if cmd_buffer.startswith("cd "):
                    prefix, suggestion, is_dir = find_autocomplete_suggestion(
                        cmd_buffer, current_path
                    )
                    cmd_buffer = "cd " + prefix + suggestion
                continue

            else:
                try:
                    ch = chr(key)
                    if ch.isprintable():
                        cmd_buffer += ch
                        new_sel = update_selection_from_regex(cmd_buffer, entries)
                        if new_sel is not None:
                            selected = new_sel
                except:
                    pass
                continue

        key = stdscr.getch()
        if last_search and key in (ord("n"), ord("N")):
            if not search_matches:
                _show_status(stdscr, "No matches", duration=1.0)
            else:
                if key == ord("n"):
                    current_match_idx = (current_match_idx + 1) % len(search_matches)
                else:
                    current_match_idx = (current_match_idx - 1) % len(search_matches)
                selected = search_matches[current_match_idx]
                stdscr.clear()
                continue

        if key == ord("a"):
            new_item = create_entity(stdscr, current_path)
            if new_item:
                entries = [".."] + sorted(os.listdir(current_path))
                if new_item in entries:
                    selected = entries.index(new_item)
            stdscr.clear()
            continue

        if key == ord("A"):
            entries = [".."] + sorted(os.listdir(current_path))
            if selected < len(entries):
                target = entries[selected]
                full_target = os.path.join(current_path, target)
                if os.path.isdir(full_target) and target not in (".", ".."):
                    new_item = create_entity(stdscr, full_target)
                    # keep selection on original directory
            stdscr.clear()
            continue

        if key == ord("r"):
            entries = [".."] + sorted(os.listdir(current_path))
            new_name = rename_entity(stdscr, current_path, entries, selected)
            if new_name:
                entries = [".."] + sorted(os.listdir(current_path))
                if new_name in entries:
                    selected = entries.index(new_name)
            stdscr.clear()
            continue

        if key == ord("d"):
            entries = [".."] + sorted(os.listdir(current_path))
            delete_entity(stdscr, current_path, entries, selected)
            stdscr.clear()
            continue

        if (key == curses.KEY_UP or key == ord("k")) and selected > 0:
            selected -= 1

        elif (key == curses.KEY_DOWN or key == ord("j")) and selected < n - 1:
            selected += 1

        elif key == curses.KEY_LEFT or key == ord("h"):
            parent = os.path.dirname(current_path)
            if os.path.isdir(parent) and parent != current_path:
                current_path = parent
                selected = 0

        elif key == curses.KEY_RIGHT or key == ord("l"):
            picked = entries[selected]
            full = os.path.normpath(os.path.join(current_path, picked))
            if os.path.isdir(full):
                current_path = full
                selected = 0

        elif key == ord("\n"):
            picked = entries[selected]
            full = os.path.normpath(os.path.join(current_path, picked))
            if os.path.isdir(full):
                current_path = full
                selected = 0
            else:
                try:
                    curses.endwin()
                    if os.environ.get("PYPATH_MODE") == "neovim":
                        cache = os.path.expanduser("~/.pypath_last")
                        try:
                            with open(cache, "w", encoding="utf-8") as f:
                                f.write(full + "\n")
                        except Exception:
                            pass
                        sys.exit(0)

                    editor = os.environ.get("EDITOR", "vim")
                    ret = os.system(f"{editor} {full}")
                    if ret != 0:
                        curses.wrapper(
                            lambda scr: _show_error_curses(
                                scr, f"Error running '{editor}' (code {ret})"
                            )
                        )
                    stdscr.clear()
                    curses.curs_set(0)
                except Exception as e:
                    curses.wrapper(
                        lambda scr: _show_error_curses(scr, f"Exception: {e}")
                    )

        elif key == ord("c") or key == ord(":") or key == ord("/"):
            command_mode = True
            cmd_buffer = "" if key != ord("/") else "/"
            stdscr.clear()
            curses.curs_set(1)
            continue

        elif key == ord("p"):
            preview_mode = not preview_mode
            stdscr.clear()
            curses.curs_set(0)
            continue
        elif key == ord("C"):
            entries = [".."] + sorted(os.listdir(current_path))
            if selected < len(entries):
                copy_entity(stdscr, current_path, entries, selected)
        elif key == ord("X"):
            entries = [".."] + sorted(os.listdir(current_path))
            if selected < len(entries):
                cut_entity(stdscr, current_path, entries, selected)
        elif key == ord("P"):
            paste_entity(stdscr, current_path)
            entries = [".."] + sorted(os.listdir(current_path))

        elif key == ord("q"):
            break

    curses.endwin()


if __name__ == "__main__":
    curses.wrapper(main)
