"""
visualize_dynamic_groups.py — Interactive visualization of dynamic classification results.

Reads from output/dynamic_checkpoint.json or output/dynamic_groups.json
and generates an interactive HTML dashboard with:
  - Treemap of groups and species
  - Bar chart of species per group
  - Sunburst chart by habitat → trophic → group
"""

import json
import sys
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

OUTPUT_DIR = Path(__file__).parent / "output"

# ── Load data ─────────────────────────────────────────────────────────

def load_groups() -> list:
    """Load groups from final output or checkpoint."""
    final_path = OUTPUT_DIR / "dynamic_groups.json"
    ckpt_path = OUTPUT_DIR / "dynamic_checkpoint.json"

    if final_path.exists():
        with open(final_path, encoding="utf-8") as f:
            return json.load(f)
    elif ckpt_path.exists():
        with open(ckpt_path, encoding="utf-8") as f:
            data = json.load(f)
            groups_dict = data.get("groups", {})
            groups_list = []
            for gid, g in sorted(groups_dict.items()):
                groups_list.append({
                    "group_id": g.get("group_id", gid),
                    "group_name": g.get("group_name", gid),
                    "description": g.get("description", ""),
                    "habitat": g.get("habitat", "unknown"),
                    "trophic_level": g.get("trophic_level", "unknown"),
                    "size_class": g.get("size_class", "unknown"),
                    "taxonomic_affinity": g.get("taxonomic_affinity", ""),
                    "species": g.get("species", []),
                    "species_count": len(g.get("species", [])),
                })
            return groups_list
    else:
        print("❌ No groups data found in output/")
        sys.exit(1)


def main():
    groups = load_groups()
    total_species = sum(g["species_count"] for g in groups)
    total_groups = len(groups)

    print(f"Loaded {total_groups} groups with {total_species} species total")

    # ── 1. TREEMAP: Groups and their species ──────────────────────

    treemap_ids = ["All Groups"]
    treemap_parents = [""]
    treemap_values = [0]
    treemap_colors = [""]
    treemap_text = [""]

    # Color map by habitat
    habitat_colors = {
        "terrestrial": "#2ecc71",
        "marine": "#3498db",
        "pelagic": "#2980b9",
        "benthic": "#1abc9c",
        "demersal": "#16a085",
        "freshwater": "#9b59b6",
        "intertidal": "#e67e22",
        "reef": "#e74c3c",
        "unknown": "#95a5a6",
    }

    for g in groups:
        gid = g["group_id"]
        gname = g["group_name"]
        habitat = g["habitat"].split("/")[0].split(",")[0].strip().lower()
        color = habitat_colors.get(habitat, "#95a5a6")

        # Group node
        label = f"{gid}: {gname}"
        treemap_ids.append(label)
        treemap_parents.append("All Groups")
        treemap_values.append(g["species_count"])
        treemap_colors.append(color)
        treemap_text.append(
            f"Habitat: {g['habitat']}<br>"
            f"Trophic: {g['trophic_level']}<br>"
            f"Size: {g['size_class']}<br>"
            f"Species: {g['species_count']}"
        )

        # Species nodes
        for sp in g.get("species", []):
            treemap_ids.append(f"{sp} ({gid})")
            treemap_parents.append(label)
            treemap_values.append(1)
            treemap_colors.append(color)
            treemap_text.append(f"{sp}<br>Group: {gname}")

    fig_treemap = go.Figure(go.Treemap(
        ids=treemap_ids,
        labels=[x.split(" (FG")[0] if " (FG" in x else x for x in treemap_ids],
        parents=treemap_parents,
        values=treemap_values,
        marker=dict(colors=treemap_colors),
        hovertext=treemap_text,
        hoverinfo="text",
        textinfo="label+value",
        maxdepth=2,
    ))
    fig_treemap.update_layout(
        title=f"Functional Groups Treemap ({total_groups} groups, {total_species} species)",
        margin=dict(t=50, l=10, r=10, b=10),
        height=700,
    )

    # ── 2. BAR CHART: Species count per group ─────────────────────

    groups_sorted = sorted(groups, key=lambda g: g["species_count"], reverse=True)
    bar_labels = [f"{g['group_id']}: {g['group_name'][:30]}" for g in groups_sorted]
    bar_values = [g["species_count"] for g in groups_sorted]
    bar_habitats = [g["habitat"].split("/")[0].split(",")[0].strip().lower() for g in groups_sorted]
    bar_colors = [habitat_colors.get(h, "#95a5a6") for h in bar_habitats]

    fig_bar = go.Figure(go.Bar(
        x=bar_values,
        y=bar_labels,
        orientation="h",
        marker_color=bar_colors,
        text=bar_values,
        textposition="outside",
        hovertemplate="%{y}<br>Species: %{x}<extra></extra>",
    ))
    fig_bar.update_layout(
        title="Species per Functional Group",
        xaxis_title="Number of Species",
        yaxis=dict(autorange="reversed"),
        height=max(400, total_groups * 30),
        margin=dict(l=250, r=50, t=50, b=40),
    )

    # ── 3. SUNBURST: Habitat → Trophic → Group ───────────────────

    sun_ids = []
    sun_labels = []
    sun_parents = []
    sun_values = []

    # Build hierarchy
    hierarchy = {}  # habitat -> trophic -> [(group_name, count)]
    for g in groups:
        h = g["habitat"].split("/")[0].split(",")[0].strip().lower() or "unknown"
        t = g["trophic_level"].split("/")[0].strip().lower() or "unknown"
        hierarchy.setdefault(h, {}).setdefault(t, []).append(
            (g["group_id"], g["group_name"], g["species_count"])
        )

    # Root
    sun_ids.append("Ecosystem")
    sun_labels.append("Ecosystem")
    sun_parents.append("")
    sun_values.append(0)

    for hab, trophics in sorted(hierarchy.items()):
        # Habitat level
        hab_id = f"hab_{hab}"
        sun_ids.append(hab_id)
        sun_labels.append(hab.capitalize())
        sun_parents.append("Ecosystem")
        sun_values.append(0)

        for troph, group_list in sorted(trophics.items()):
            # Trophic level
            troph_id = f"{hab_id}_{troph}"
            sun_ids.append(troph_id)
            sun_labels.append(troph.replace("_", " ").capitalize())
            sun_parents.append(hab_id)
            sun_values.append(0)

            for gid, gname, count in group_list:
                # Group level
                g_id = f"{troph_id}_{gid}"
                sun_ids.append(g_id)
                sun_labels.append(f"{gid}: {gname[:25]}")
                sun_parents.append(troph_id)
                sun_values.append(count)

    fig_sunburst = go.Figure(go.Sunburst(
        ids=sun_ids,
        labels=sun_labels,
        parents=sun_parents,
        values=sun_values,
        branchvalues="total",
        hovertemplate="<b>%{label}</b><br>Species: %{value}<extra></extra>",
        maxdepth=3,
    ))
    fig_sunburst.update_layout(
        title="Ecosystem Structure: Habitat → Trophic Level → Functional Group",
        height=700,
        margin=dict(t=50, l=10, r=10, b=10),
    )

    # ── 4. COMBINED HTML DASHBOARD ─────────────────────────────────

    html_path = OUTPUT_DIR / "dynamic_groups_dashboard.html"

    with open(html_path, "w", encoding="utf-8") as f:
        f.write("""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Functional Groups Dashboard</title>
<style>
  body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
  h1 { color: #2c3e50; text-align: center; }
  .stats { display: flex; justify-content: center; gap: 30px; margin: 20px 0; }
  .stat-box { background: white; padding: 20px 30px; border-radius: 10px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }
  .stat-num { font-size: 2em; font-weight: bold; color: #3498db; }
  .stat-label { color: #7f8c8d; }
  .chart-container { background: white; margin: 20px 0; padding: 15px;
                     border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
  .legend { display: flex; flex-wrap: wrap; justify-content: center;
            gap: 15px; margin: 15px 0; }
  .legend-item { display: flex; align-items: center; gap: 5px; font-size: 0.9em; }
  .legend-dot { width: 14px; height: 14px; border-radius: 3px; }
</style>
</head><body>
""")
        f.write(f"<h1>🌊 Dynamic Functional Groups Classification</h1>\n")
        f.write(f"""<div class="stats">
  <div class="stat-box"><div class="stat-num">{total_species}</div><div class="stat-label">Species Classified</div></div>
  <div class="stat-box"><div class="stat-num">{total_groups}</div><div class="stat-label">Functional Groups</div></div>
  <div class="stat-box"><div class="stat-num">{total_species/total_groups:.1f}</div><div class="stat-label">Avg Species/Group</div></div>
</div>\n""")

        # Habitat color legend
        used_habitats = set()
        for g in groups:
            h = g["habitat"].split("/")[0].split(",")[0].strip().lower()
            used_habitats.add(h)

        f.write('<div class="legend">\n')
        for h in sorted(used_habitats):
            c = habitat_colors.get(h, "#95a5a6")
            f.write(f'  <div class="legend-item"><div class="legend-dot" style="background:{c}"></div>{h.capitalize()}</div>\n')
        f.write('</div>\n')

        # Embed charts
        f.write('<div class="chart-container">\n')
        f.write(fig_treemap.to_html(full_html=False, include_plotlyjs="cdn"))
        f.write('\n</div>\n')

        f.write('<div class="chart-container">\n')
        f.write(fig_sunburst.to_html(full_html=False, include_plotlyjs=False))
        f.write('\n</div>\n')

        f.write('<div class="chart-container">\n')
        f.write(fig_bar.to_html(full_html=False, include_plotlyjs=False))
        f.write('\n</div>\n')

        # Groups table
        f.write("""
<div class="chart-container">
<h2 style="color:#2c3e50">Group Details</h2>
<table style="width:100%; border-collapse:collapse; font-size:0.9em;">
<tr style="background:#3498db; color:white;">
  <th style="padding:8px; text-align:left;">ID</th>
  <th style="padding:8px; text-align:left;">Group Name</th>
  <th style="padding:8px;">Habitat</th>
  <th style="padding:8px;">Trophic Level</th>
  <th style="padding:8px;">Size</th>
  <th style="padding:8px;">Species</th>
  <th style="padding:8px; text-align:left;">Sample Species</th>
</tr>
""")
        for i, g in enumerate(groups_sorted):
            bg = "#f8f9fa" if i % 2 == 0 else "white"
            sample = ", ".join(g["species"][:3])
            if g["species_count"] > 3:
                sample += f" (+{g['species_count']-3})"
            f.write(f"""<tr style="background:{bg};">
  <td style="padding:6px; font-weight:bold;">{g['group_id']}</td>
  <td style="padding:6px;">{g['group_name']}</td>
  <td style="padding:6px; text-align:center;">{g['habitat']}</td>
  <td style="padding:6px; text-align:center;">{g['trophic_level']}</td>
  <td style="padding:6px; text-align:center;">{g['size_class']}</td>
  <td style="padding:6px; text-align:center; font-weight:bold;">{g['species_count']}</td>
  <td style="padding:6px; font-style:italic; font-size:0.85em;">{sample}</td>
</tr>\n""")

        f.write("</table>\n</div>\n</body></html>")

    print(f"\n✅ Dashboard saved: {html_path}")
    print(f"   Open in browser to explore interactively.")

    # Auto-open in default browser
    import webbrowser
    webbrowser.open(str(html_path))


if __name__ == "__main__":
    main()
