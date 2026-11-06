# Profile maintenance

The profile uses the [Catppuccin Macchiato palette](https://catppuccin.com/palette/).
`scripts/render_profile.py` builds the SVG charts from GitHub activity and
repository totals.
Images and tool logos are stored in this repository.

## Data

- Repository and star counts combine the public repository API with
  [the private aggregate snapshot](../data/private-totals.json). Repository
  totals include public and private forks, archives, and this profile. Stars
  exclude forks. The snapshot stores only its date, repository count, and star
  count; private repository names and descriptions are never published.
- Contributions come from the same anonymous, public calendar shown on the
  GitHub profile. They include whatever anonymized private activity the account
  has already chosen to show publicly; no private repository data is requested.
- Active days count days with at least one contribution in that calendar.
  Narrow screens use a 26-week calendar so its cells and labels stay readable;
  the totals still cover the full year.
- The weekly chart groups the last twelve calendar weeks, Sunday through
  Saturday. The current week is incomplete.
- Skills list tools used in public and private projects. It reflects languages,
  dependencies, and project configuration, without proficiency ratings or private
  project names.
- The expanded project list includes public, non-fork, non-archived repositories
  beyond the four selected projects.

## Refresh

[Refresh profile](https://github.com/oNxZero/oNxZero/actions/workflows/profile.yml)
runs daily at 05:23 UTC, on generator changes, or manually through **Run workflow**.
Daily activity and public totals use the built-in `GITHUB_TOKEN`. Private totals
use the committed snapshot, refreshed locally when needed. The generator collects
and validates all data before
writing assets. If a source request or calendar parse fails, the existing assets
remain in place and the workflow reports the error.

To render locally with Python 3.11 or later:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/render_profile.py
```

Optionally set `GH_TOKEN` for higher API rate limits. Only `api.github.com`
receives this token. Local runs also work without authentication.

To refresh the private totals, run with an owner-authenticated `GH_TOKEN`:

```bash
python3 scripts/render_profile.py --refresh-private
```

This writes only aggregate counts to `data/private-totals.json`. Commit that file
with the refreshed artwork. Private totals remain at the snapshot date between
these refreshes; contribution graphs continue updating daily.

If automatic private-total refresh is wanted later, add a dedicated read-only
owner token as the `PROFILE_STATS_TOKEN` Actions secret, with metadata access to
all owned repositories. The workflow supports it already. The token stays in
Actions secrets and is never written into an SVG or committed data.

For working on the artwork without fetching data again:

```bash
python3 scripts/render_profile.py --save-data .cache/profile.json
python3 scripts/render_profile.py --from-data .cache/profile.json
```

Edit project descriptions and colors in `scripts/render_profile.py`.
Edit the README directly; the generator replaces only its `PROJECTS` block.

## Logos

Technology artwork comes from
[Devicon](https://github.com/devicons/devicon), with its
[MIT license](../assets/logos/DEVICON-LICENSE.txt) included. Logos keep their
original colors and identify the tools used by these projects. GTK's mark comes
from [Simple Icons](https://simpleicons.org/), with its
[CC0 license](../assets/logos/SIMPLE-ICONS-LICENSE.txt) included.

The project cards reuse the existing Automater, CTM Generator, and Spuds Shop
artwork. Not Enough Revives uses the Java mark because it has no published
project logo in its source repository. Every project card links to its repository.
