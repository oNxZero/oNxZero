# Profile maintenance

The profile uses the [Catppuccin Macchiato palette](https://catppuccin.com/palette/).
`scripts/render_profile.py` builds the SVG charts from public GitHub data.
Images and tool logos are stored in this repository.

## Data

- Repository and star counts come from GitHub's public user/repository API.
  The repository count includes public forks and this profile. Stars exclude forks.
- Contributions come from the same anonymous, public calendar shown on the
  GitHub profile. They include whatever anonymized private activity the account
  has already chosen to show publicly; no private repository data is requested.
- Active days count days with at least one contribution in that calendar.
  Narrow screens use a 26-week calendar so its cells and labels stay readable;
  the totals still cover the full year.
- The weekly chart groups the last twelve calendar weeks, Sunday through
  Saturday. The current week is incomplete.
- Language percentages use GitHub's detected source bytes across public,
  non-fork, non-archived repositories, excluding this profile repository.
  Percentages describe repository contents.
- The expanded project list includes public, non-fork, non-archived repositories
  beyond the four selected projects.

## Refresh

[Refresh profile](https://github.com/oNxZero/oNxZero/actions/workflows/profile.yml)
runs daily at 05:23 UTC, on generator changes, or manually through **Run workflow**.
It uses the repository's built-in `GITHUB_TOKEN`; no personal access token or
extra secrets are needed. The generator collects and validates all data before
writing assets. If a source request or calendar parse fails, the existing assets
remain in place and the workflow reports the error.

To render locally with Python 3.11 or later:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/render_profile.py
```

Optionally set `GH_TOKEN` for higher API rate limits. Only `api.github.com`
receives this token. Local runs also work without authentication.

For working on the artwork without fetching data again:

```bash
python3 scripts/render_profile.py --save-data .cache/profile.json
python3 scripts/render_profile.py --from-data .cache/profile.json
```

Edit project descriptions and colors in `scripts/render_profile.py`.
Edit the README directly; the generator replaces only its `PROJECTS` block.

## Logos

Python, Java, Linux and Git artwork comes from
[Devicon](https://github.com/devicons/devicon), with its
[MIT license](../assets/logos/DEVICON-LICENSE.txt) included. Logos keep their
original colors and identify the tools used by these projects.
