# Practice Log PDF Generator

This generator creates US Letter practice-log sheets from a YAML or JSON definition.

## Pagination rule

The whole log is one table that splits across pages by rows, except:

1. A `repeats_each` block is never split across pages.
2. A unit title or section row always stays on the same page as the exercises that follow it.

Each continuation page starts with "(continued)".

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
    sessions: 6

contents:
  units:
    - unit: Rock Bass Unit 1
      exercises:
        - Exercise 1
        - Exercise 2
    - unit: Rock Bass Unit 2
      exercises:
        - Exercise 1
```

Each unit's title is a merged row inside the table, in a bold version of the
table font at the table font size. A unit with a blank `unit:` gets no title
row. An exercise with no name prints an empty row.

`config.table.sessions` sets the number of practice-session columns; it can
also be set under `contents`.

### Repeating exercises

Both options default to `1` and must be at least `1`. Set under `contents`,
`repeats_each` is the default for every unit and `repeats` repeats the whole
table. Set on a unit, they apply to that unit only.

`repeats` prints the exercise list the given number of times:

```yaml
- unit: Groove Drills
  repeats: 2
  exercises: [Exercise 1, Exercise 2, Exercise 3]
  # Rows: 1, 2, 3, 1, 2, 3
```

A heavier rule (`config.style.repeat_line_width`) marks the end of each
pass through the list. A unit's title row is printed once, before the first
pass.

`repeats_each` (or `repeats-each`) prints each exercise the given number of
times in a row before moving to the next one:

```yaml
- unit: Scale Drills
  repeats_each: 2
  exercises: [Exercise 1, Exercise 2, Exercise 3]
  # Rows: 1, 1, 2, 2, 3, 3
```

A slightly heavier rule (`config.style.outer_line_width`) separates each
exercise's group of rows.

The two options can be combined. `repeats_each` is applied first, then the
resulting list is repeated:

```yaml
- unit: Combined
  repeats: 2
  repeats_each: 3
  exercises: [A, B]
  # Rows: A, A, A, B, B, B, A, A, A, B, B, B
```

### Section rows

A `section` entry adds a label row inside the table. It is one merged cell
the full width of the table, the same height as an exercise row, in an italic
version of the table font at the table font size:

```yaml
- unit: Hanon
  exercises:
    - section: Left hand
    - Exercise 1
    - Exercise 2
    - section: Right hand
    - Exercise 3
```

A `- section:` entry can also sit between units in `contents.units`. Section
rows are printed once, not repeated by `repeats_each`, but they are repeated
with the list by `repeats`.

## Appearance controls

The YAML `config.style` section controls:

- document title font, size and gap below it
- running header (document title on later pages) font, size and position
- table font and font size (`font`, `table_font_size`)
- unit title and section fonts (`unit_font`, `section_font`; by default the
  bold and italic versions of `font`)
- "(continued)" font, size and gap
- row height
- exercise-column width
- line widths (`line_width`, `outer_line_width`, `repeat_line_width`)
- cell padding

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
