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
- Contributions come from GitHub's GraphQL contribution calendar, including
  anonymized private activity shared through **Contribution settings → Private
  contributions**. The yearly total, heatmap, active days, and weekly chart all
  use that single calendar. The daily counts and restricted contribution count
  are saved in [an aggregate snapshot](../data/activity.json); it contains no
  repository names, commit messages, or other private project details.
- Turning off private contributions would make the public feed incomplete.
  If GitHub stops returning private counts after previously including them,
  the refresh fails and keeps the previous charts and their displayed date.
  It never silently replaces them with public-only activity.
- Active days count days with at least one contribution in that calendar.
  Narrow screens use a 26-week calendar so its cells and labels stay readable;
  the totals still cover the full year.
- The weekly chart groups the last twelve calendar weeks, Sunday through
  Saturday. The current week is incomplete.
- The 12 skills list tools used in public and private projects. It reflects languages,
  dependencies, and project configuration, without proficiency ratings or private
  project names.
- The expanded project list includes public, non-fork, non-archived repositories
  beyond the four selected projects.

## Refresh

[Refresh profile](https://github.com/oNxZero/oNxZero/actions/workflows/profile.yml)
runs hourly at minute 23, on generator changes, or manually through **Run workflow**.
GitHub may delay scheduled runs during busy periods. Activity and public totals
use the built-in `GITHUB_TOKEN`. Private repository totals refresh on every run
when `PROFILE_STATS_TOKEN` is configured; otherwise they use the committed
snapshot, refreshed locally when needed. The generator collects
and validates all data before
writing assets. If a source request or calendar parse fails, the existing assets
remain in place and the workflow reports the error.

To render locally with Python 3.11 or later:

```bash
python3 -m unittest discover -s tests -v
GH_TOKEN="$(gh auth token)" python3 scripts/render_profile.py
```

Set `GH_TOKEN` for the GraphQL API. Only `api.github.com` receives this token.
The workflow uses its built-in token; it needs no access to other repositories
to read the anonymized private counts shared on the public profile.

To refresh the private totals, run with an owner-authenticated `GH_TOKEN`:

```bash
python3 scripts/render_profile.py --refresh-private
```

This writes only aggregate counts to `data/private-totals.json`. Commit that file
with the refreshed artwork. Private totals remain at the snapshot date between
these refreshes; contribution graphs continue updating hourly.

To enable automatic private-total refresh:

1. [Create a fine-grained personal access token](https://github.com/settings/personal-access-tokens/new?name=Profile%20stats&target_name=oNxZero&metadata=read)
   with **oNxZero** as the resource owner, **All repositories**, and only
   **Metadata: Read-only** repository permission. All repositories includes
   future repositories, so newly created projects are counted too.
2. [Add it as an Actions repository secret](https://github.com/oNxZero/oNxZero/settings/secrets/actions/new)
   named **PROFILE_STATS_TOKEN**.
3. Run **Refresh profile** once, or wait for the next scheduled run. The workflow
   refreshes the aggregate private counts before rebuilding the charts.

The token stays in Actions secrets and is never written into an SVG or
committed data. It does not need access to repository contents or write access.
The private totals file records the date of the last successful refresh.

For working on the artwork without fetching data again:

```bash
python3 scripts/render_profile.py --save-data .cache/profile.json
python3 scripts/render_profile.py --from-data .cache/profile.json
```

Edit project descriptions and colors in `scripts/render_profile.py`.
Edit the README directly; the generator replaces only its `PROJECTS` block.

## GitHub's own profile sections

The README cannot change GitHub's surrounding profile layout. GitHub's
[private-profile setting](https://docs.github.com/en/account-and-profile/how-tos/profile-customization/setting-your-profile-to-private)
hides the native contribution graph and activity from visitors, while keeping
the README visible. It also hides follower counts, Follow and Sponsor buttons,
and other social features; the owner still sees their own activity.
There is no separate switch to remove just the native graph and timeline.
Pinning projects replaces Popular repositories with Pinned; it does not remove
that section.

## Logos

Technology artwork comes from
[Devicon](https://github.com/devicons/devicon), with its
[MIT license](../assets/logos/DEVICON-LICENSE.txt) included. Logos keep their
original colors and identify the tools used by these projects. GTK's mark comes
from [Simple Icons](https://simpleicons.org/), with its
[CC0 license](../assets/logos/SIMPLE-ICONS-LICENSE.txt) included.

The project cards reuse the existing CTM Generator, Moonlight, Automater, and
Spuds Shop artwork.
Every project card links to its repository, and each skill tile links to its
official language, framework, or tool site.

## Typography and icons

The artwork uses Space Grotesk for headings and body text, and JetBrains Mono
for numbers and technology labels. The original fonts and their OFL licenses
are in `assets/fonts/`. Glyph outlines are embedded into each SVG, so GitHub
does not need to load fonts or rely on the viewer's installed fonts.

`scripts/build_font_atlas.py` rebuilds `assets/fonts/atlas.json` from those fonts.
It requires FontTools; daily refreshes read the atlas using the standard library.

Chart and link icons come from [Lucide](https://lucide.dev/), with its
[license](../assets/icons/LUCIDE-LICENSE.txt) included.
