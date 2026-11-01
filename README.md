# Practice Log PDF Generator

This generator creates US Letter practice-log sheets from a YAML or JSON definition.

## Pagination rule

For each unit:

1. The unit title and table are treated as one block.
2. If the entire block fits in the remaining space on the current page, it is placed there.
3. If it does not fit in the remaining space, but would fit on a fresh page, it is moved intact to the next page.
4. If the unit itself is taller than a complete page, the table is allowed to split by rows. The column-header row repeats on continuation pages.

This is the behavior that Google Sheets does not express cleanly with custom page breaks.

## Run

```bash
python gen_log.py practice_logs.yaml practice_logs.pdf
```

Dependencies:

```bash
pip install reportlab pyyaml
```

## Input

```yaml
config:
  table:
    sessions: 7

units:
  - title: Rock Bass Unit 1
    exercises:
      - Exercise 1
      - Exercise 2
      - Exercise 3
```

Each unit may override the number of practice-session columns:

```yaml
- title: Rock Bass Unit 4
  sessions: 6
  exercises:
    - Exercise 1
    - Exercise 2
```

You can also put labels in the session columns:

```yaml
session_headers: ["1", "2", "3", "4", "5", "6", "7"]
```

Leaving `exercise_header` blank (in `config.table` or on a unit) removes the
header row entirely:

```yaml
exercise_header:
```

### Repeating exercises

A unit can list its exercises more than once without repeating them in the
YAML. Both options default to `1` and must be at least `1`.

`repeats` prints the whole exercise list the given number of times:

```yaml
- title: Groove Drills
  repeats: 2
  exercises: [Exercise 1, Exercise 2, Exercise 3]
  # Rows: 1, 2, 3, 1, 2, 3
```

A heavier rule (`config.style.repeat_line_width`) marks the end of each
pass through the list.

`repeats_each` (or `repeats-each`) prints each exercise the given number of
times in a row before moving to the next one:

```yaml
- title: Scale Drills
  repeats_each: 2
  exercises: [Exercise 1, Exercise 2, Exercise 3]
  # Rows: 1, 1, 2, 2, 3, 3
```

A slightly heavier rule (`config.style.outer_line_width`) separates each
exercise's group of rows.

The two options can be combined. `repeats_each` is applied first, then the
resulting list is repeated:

```yaml
- title: Combined
  repeats: 2
  repeats_each: 3
  exercises: [A, B]
  # Rows: A, A, A, B, B, B, A, A, A, B, B, B
```

A `repeats_each` block is never split across pages.

### Section rows

A `section` entry adds a heading row inside the table. It is one merged cell
the full width of the table, the same height as an exercise row, in a bold
version of the table font:

```yaml
- title: Hanon
  exercises:
    - section: Left hand
    - Exercise 1
    - Exercise 2
    - section: Right hand
    - Exercise 3
```

A section row always stays on the same page as the exercise that follows it
(the whole block when `repeats_each` is used). Section rows are printed once,
not repeated by `repeats_each`, but they are repeated with the list by
`repeats`. Set `config.style.section_font` to use a different font.

## Appearance controls

The YAML `config.style` section controls:

- title font and size
- table font size
- row height
- header-row height
- exercise-column width
- border thickness
- cell padding
- spacing between title and table
- spacing between units

The `config.page` section controls margins and portrait/landscape orientation.

## Lined paper

`gen_paper.py` creates a double-sided sheet of plain lined paper. Its only
argument is the line spacing in millimeters:

```bash
python gen_paper.py 7
```

This writes `pdfs/lined-paper-7mm.pdf`, a two-page B5 PDF:

- Page 1 is the front and page 2 is the back.
- A 0.5" gutter for punched holes sits on the left of the front and the right
  of the back, so the two line up when printed double-sided.
- The other margins are 0.25", and lines run the full width between the
  gutter and the outside margin. The first and last lines are black; the rest
  are light gray.

The page size, gutter, margins, line color and line width are constants at the
top of the script.

## Exact visual matching

The supplied Google Sheets URL could not be fetched from the current environment, so the included defaults are a clean approximation of the structure described in the conversation rather than a pixel-for-pixel transcription.

To match the existing Rock Bass sheets exactly, provide either:

- a PDF exported from Google Sheets, or
- screenshots of one or two representative pages.

Then the dimensions in `config.style` can be calibrated against the original.
