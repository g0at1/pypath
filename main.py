#!/usr/bin/env python3
import curses
import os
import stat
import pwd
import grp
import time
import subprocess
import re


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
    lines = message.split("\n")
    box_w = max(len(line) for line in lines) + 4
    box_h = len(lines) + 4
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
    new_path = current_path

    for part in parts:
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
                current_path = execute_command(stdscr, cmd_buffer, current_path)
                cmd_buffer = ""
                command_mode = False
                stdscr.clear()
                curses.curs_set(0)
                selected = 0
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
                except:
                    pass
                continue

        key = stdscr.getch()

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

        elif key == ord("c") or key == ord(":"):
            command_mode = True
            cmd_buffer = ""
            stdscr.clear()
            curses.curs_set(1)
            continue

        elif key == ord("p"):
            preview_mode = not preview_mode
            stdscr.clear()
            curses.curs_set(0)
            continue

        elif key == ord("q"):
            break

    curses.endwin()


if __name__ == "__main__":
    curses.wrapper(main)
