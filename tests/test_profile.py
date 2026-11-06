from datetime import date
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("profile_renderer", Path(__file__).resolve().parents[1] / "scripts/render_profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class CalendarTests(unittest.TestCase):
    def parse(self, markup):
        parser = profile.CalendarParser()
        parser.feed(markup)
        return parser

    def test_calendar_uses_tooltip_counts_and_ignores_future_days(self):
        markup = '''
          <td id="today" data-date="2026-11-06" data-level="4"></td>
          <tool-tip for="today"><span>1,234 contributions</span> on November 6th.</tool-tip>
          <td id="future" data-date="2026-11-07" data-level="0"></td>
        '''
        self.assertEqual(self.parse(markup).days(date(2026, 11, 6), minimum=1), [
            {"date": "2026-11-06", "level": 4, "count": 1234},
        ])

    def test_changed_markup_fails_instead_of_fabricating_zero_activity(self):
        parser = self.parse('<td id="day" data-date="2026-11-06" data-level="1"></td>')
        with self.assertRaises(ValueError):
            parser.days(date(2026, 11, 6), minimum=1)
        with self.assertRaises(ValueError):
            self.parse("<div>GitHub is unavailable</div>").days(date(2026, 11, 6))

    def test_missing_days_are_rejected(self):
        markup = '''
          <td id="a" data-date="2026-11-04" data-level="0"></td>
          <tool-tip for="a">No contributions on November 4th.</tool-tip>
          <td id="b" data-date="2026-11-06" data-level="1"></td>
          <tool-tip for="b">1 contribution on November 6th.</tool-tip>
        '''
        with self.assertRaises(ValueError):
            self.parse(markup).days(date(2026, 11, 6), minimum=2)


class AggregationTests(unittest.TestCase):
    def test_weeks_cross_year_boundary_and_exclude_future_contributions(self):
        weeks = profile.weekly_counts([
            {"date": "2025-12-27", "count": 100},
            {"date": "2025-12-28", "count": 2},
            {"date": "2026-01-03", "count": 3},
            {"date": "2026-01-04", "count": 7},
            {"date": "2026-01-06", "count": 100},
        ], date(2026, 1, 5), count=2)
        self.assertEqual(weeks, [(date(2025, 12, 28), 5), (date(2026, 1, 4), 7)])

    def test_public_projects_exclude_private_fork_archive_and_profile(self):
        repos = [{"name": name, "private": private, "fork": fork, "archived": archived}
                 for name, private, fork, archived in [
                     ("tool", False, False, False), ("secret", True, False, False),
                     ("fork", False, True, False), ("archive", False, False, True),
                     ("ONXZERO", False, False, False),
                 ]]
        self.assertEqual([r["name"] for r in profile.public_project_repos(repos)], ["tool"])

    def test_private_snapshot_rejects_repository_names(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "totals.json"
            path.write_text(json.dumps({"updated": "2026-11-06", "repository_count": 1,
                                        "stars_received": 0, "repository_names": ["private-project"]}))
            with self.assertRaises(ValueError):
                profile.read_private_totals(path)

    def test_private_refresh_publishes_only_aggregate_counts(self):
        responses = [{"login": profile.USER, "owned_private_repos": 2}, [
            {"name": "private-project", "private": True, "owner": {"login": profile.USER}, "stargazers_count": 3, "fork": False},
            {"name": "private-fork", "private": True, "owner": {"login": profile.USER}, "stargazers_count": 9, "fork": True},
        ]]
        with tempfile.TemporaryDirectory() as temp, patch.object(profile, "ROOT", Path(temp)), \
                patch.object(profile, "api", side_effect=responses), patch.dict("os.environ", {"GH_TOKEN": "test-token"}):
            result = profile.refresh_private_totals(date(2026, 11, 6))
            self.assertEqual(result, {"updated": "2026-11-06", "repository_count": 2, "stars_received": 3})
            saved = (Path(temp) / "data/private-totals.json").read_text()
            self.assertNotIn("private-project", saved)
            self.assertNotIn("test-token", saved)

    def test_insufficient_private_access_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(profile, "ROOT", Path(temp)), \
                patch.object(profile, "api", side_effect=[{"login": profile.USER, "owned_private_repos": 3}, []]), \
                patch.dict("os.environ", {"GH_TOKEN": "test-token"}):
            target = Path(temp) / "data/private-totals.json"
            target.parent.mkdir()
            target.write_text("previous snapshot")
            with self.assertRaises(ValueError):
                profile.refresh_private_totals(date(2026, 11, 6))
            self.assertEqual(target.read_text(), "previous snapshot")

    def test_credentials_cannot_be_sent_to_an_external_api(self):
        with patch.dict("os.environ", {"GH_TOKEN": "example-test-token"}):
            with self.assertRaises(ValueError):
                profile.request("https://example.com/data", api=True)


class RenderingTests(unittest.TestCase):
    def test_chart_viewports_contain_their_frames(self):
        data = {"updated": "2026-11-06", "days": [
                    {"date": "2026-10-25", "count": 100, "level": 4},
                    {"date": "2026-11-06", "count": 3, "level": 1}],
                "repos": [], "languages": {"Python": 100, "Java": 50}}
        for compact in [False, True]:
            for renderer in [profile.activity, profile.insights]:
                with self.subTest(compact=compact, renderer=renderer.__name__):
                    root = ET.fromstring(renderer(data, compact=compact))
                    frame = root.find("{http://www.w3.org/2000/svg}rect")
                    self.assertLessEqual(float(frame.attrib["x"])+float(frame.attrib["width"]), float(root.attrib["width"]))
                    self.assertLessEqual(float(frame.attrib["y"])+float(frame.attrib["height"]), float(root.attrib["height"]))

    def test_chart_text_remains_readable_when_scaled_on_a_profile(self):
        data = {"updated": "2026-11-06", "days": [{"date": "2026-11-06", "count": 3, "level": 1}],
                "repos": [], "languages": {"Python": 100, "Java": 50}}
        for compact in [False, True]:
            for renderer in [profile.activity, profile.insights]:
                root = ET.fromstring(renderer(data, compact=compact))
                labels = [node for node in root.iter("{http://www.w3.org/2000/svg}g") if "data-label" in node.attrib]
                self.assertTrue(labels)
                for node in labels:
                    self.assertGreaterEqual(float(node.attrib["font-size"]), 18)

    def test_font_outlines_are_embedded_and_every_glyph_reference_resolves(self):
        artwork = profile.header()
        root = ET.fromstring(artwork)
        identifiers = {node.attrib["id"] for node in root.iter() if "id" in node.attrib}
        uses = list(root.iter("{http://www.w3.org/2000/svg}use"))
        self.assertTrue(uses)
        for use in uses:
            self.assertIn(use.attrib["href"][1:], identifiers)
        self.assertNotIn("@font-face", artwork)
        self.assertNotIn("https://", artwork)
        self.assertIn('data-font="Space Grotesk"', artwork)

    def test_stats_include_private_repository_totals(self):
        data = {"updated": "2026-11-06", "days": [{"date": "2026-11-06", "count": 3, "level": 1}],
                "repos": [{"fork": False, "stargazers_count": 0} for _ in range(16)],
                "private_totals": {"repository_count": 20, "stars_received": 5}}
        root = ET.fromstring(profile.activity(data))
        self.assertIn("36 public and private repositories", root.find("{http://www.w3.org/2000/svg}desc").text)
        self.assertIn("5 stars received", root.find("{http://www.w3.org/2000/svg}desc").text)

    def test_svg_text_is_escaped(self):
        for project in profile.PROJECTS:
            card = profile.project_card({**project, "title": 'Tool <x> & "y"'})
            parsed = ET.fromstring(card)
            self.assertEqual(parsed.find("{http://www.w3.org/2000/svg}title").text, 'Tool <x> & "y"')

    def test_missing_readme_markers_preserves_existing_artwork(self):
        data = {"updated": "2026-11-06", "days": [{"date": "2026-11-06", "count": 1, "level": 1}],
                "repos": [], "languages": {}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("Keep my existing README.")
            (root / "assets").mkdir()
            (root / "assets/activity.svg").write_text("previous artwork")
            with self.assertRaises(ValueError):
                profile.render(data, root)
            self.assertEqual((root / "assets/activity.svg").read_text(), "previous artwork")
            self.assertEqual((root / "README.md").read_text(), "Keep my existing README.")


if __name__ == "__main__":
    unittest.main()
