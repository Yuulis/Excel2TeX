# Excel2TeX

Excel2TeX is a Flet desktop application that converts CSV and XLSX tables into
LaTeX code.

## Development

Install dependencies with `uv` and run the application with:

```powershell
uv sync
uv run flet run src/main.py
```

Run the test suite with:

```powershell
uv run pytest
```

## Windows build

The project follows Flet's `src` layout. Build the Windows application with:

```powershell
uv run flet build windows -vv
```

Generated build files are placed under `build/` and are excluded from the
application package.
