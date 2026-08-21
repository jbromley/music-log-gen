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
python practice_log_generator.py practice_logs.yaml practice_logs.pdf
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

## Exact visual matching

The supplied Google Sheets URL could not be fetched from the current environment, so the included defaults are a clean approximation of the structure described in the conversation rather than a pixel-for-pixel transcription.

To match the existing Rock Bass sheets exactly, provide either:

- a PDF exported from Google Sheets, or
- screenshots of one or two representative pages.

Then the dimensions in `config.style` can be calibrated against the original.
