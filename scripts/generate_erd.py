"""Generate updated ERD as draw.io mxfile."""

def table(tid, name, x, y, fields):
    """fields: list of (key_type 'PK'/'FK'/'', field_name, is_separator_row)"""
    H = 30
    height = H + len(fields) * H
    out = []
    out.append(
        f'<mxCell id="{tid}" parent="1" '
        f'style="shape=table;startSize=30;container=1;collapsible=1;childLayout=tableLayout;'
        f'fixedRows=1;rowLines=0;fontStyle=1;align=center;resizeLast=1;html=1;" '
        f'value="{name}" vertex="1">'
        f'<mxGeometry height="{height}" width="200" x="{x}" y="{y}" as="geometry"/>'
        f'</mxCell>'
    )
    for i, (key, fname, sep) in enumerate(fields):
        ry = H + i * H
        bottom = "1" if sep else "0"
        rid = f"{tid}r{i}"
        fname_style = "fontStyle=5;" if key == "PK" else ""
        key_bold = "fontStyle=1;" if key in ("PK", "FK") else ""
        out.append(
            f'<mxCell id="{rid}" parent="{tid}" '
            f'style="shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;'
            f'fillColor=none;collapsible=0;dropTarget=0;points=[[0,0.5],[1,0.5]];'
            f'portConstraint=eastwest;top=0;left=0;right=0;bottom={bottom};" '
            f'value="" vertex="1">'
            f'<mxGeometry height="{H}" width="200" y="{ry}" as="geometry"/>'
            f'</mxCell>'
            f'<mxCell id="{rid}k" parent="{rid}" '
            f'style="shape=partialRectangle;connectable=0;fillColor=none;top=0;left=0;'
            f'bottom=0;right=0;{key_bold}overflow=hidden;whiteSpace=wrap;html=1;" '
            f'value="{key}" vertex="1">'
            f'<mxGeometry height="{H}" width="40" as="geometry">'
            f'<mxRectangle height="{H}" width="40" as="alternateBounds"/>'
            f'</mxGeometry></mxCell>'
            f'<mxCell id="{rid}v" parent="{rid}" '
            f'style="shape=partialRectangle;connectable=0;fillColor=none;top=0;left=0;'
            f'bottom=0;right=0;align=left;spacingLeft=6;{fname_style}overflow=hidden;'
            f'whiteSpace=wrap;html=1;" value="{fname}" vertex="1">'
            f'<mxGeometry height="{H}" width="160" x="40" as="geometry">'
            f'<mxRectangle height="{H}" width="160" as="alternateBounds"/>'
            f'</mxGeometry></mxCell>'
        )
    return "\n".join(out)


def edge(eid, src, tgt, sx=0.5, sy=1, tx=0.5, ty=0, label=""):
    lbl = f'value="{label}"' if label else 'value=""'
    return (
        f'<mxCell id="{eid}" edge="1" parent="1" source="{src}" target="{tgt}" {lbl} '
        f'style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;'
        f'exitX={sx};exitY={sy};exitDx=0;exitDy=0;'
        f'entryX={tx};entryY={ty};entryDx=0;entryDy=0;'
        f'startArrow=ERmandOne;startFill=0;endArrow=ERzeroToMany;endFill=0;">'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )


def label(lid, text, x, y):
    return (
        f'<mxCell id="{lid}" parent="1" '
        f'style="text;html=1;strokeColor=none;fillColor=none;align=center;'
        f'verticalAlign=middle;rounded=0;" value="{text}" vertex="1">'
        f'<mxGeometry height="30" width="90" x="{x}" y="{y}" as="geometry"/>'
        f'</mxCell>'
    )


# ── tables ────────────────────────────────────────────────────────────────────

SUPPLIER = table("SUP", "SUPPLIER", 310, 150, [
    ("PK", "supplier_id",       True),
    ("",   "supplier_name",     False),
    ("",   "country",           False),
    ("",   "region",            False),
    ("",   "latitude",          False),
    ("",   "longitude",         False),
    ("",   "industry",          False),
    ("",   "component_role",    False),
    ("",   "criticality",       False),   # NEW
    ("",   "current_risk_score",False),
    ("",   "risk_level",        False),
    ("",   "last_updated",      False),
])

NEWSARTICLE = table("ART", "NEWSARTICLE", 600, -40, [
    ("PK", "article_id",        True),
    ("",   "title",             False),
    ("",   "source",            False),
    ("",   "url",               False),
    ("",   "published_at",      False),
    ("",   "content",           False),
    ("",   "model_confidence",  False),
    ("",   "ingested_at",       False),
])

SUPPLYCHAIN = table("SC", "SUPPLYCHAIN", 30, 380, [
    ("PK", "supplychain_id",    True),
    ("",   "name",              False),
    ("",   "description",       False),
    ("",   "created_at",        False),
])

SC_SUP = table("SCS", "SUPPLYCHAIN_SUPPLIER", 30, 680, [
    ("PK", "id",                True),
    ("FK", "supplychain_id",    False),
    ("FK", "supplier_id",       False),
    ("",   "relation_type",     False),
])

RESI = table("RES", "RESILIENCEHISTORY", 310, 680, [
    ("PK", "id",                True),
    ("FK", "supplier_id",       False),
    ("",   "recorded_at",       False),
    ("",   "risk_score",        False),   # resilience_score removed
    ("",   "notes",             False),
])

# DISRUPTION_EVENT — 7 new fields added
DISE = table("EVT", "DISRUPTION_EVENT", 600, 250, [
    ("PK", "event_id",                      True),
    ("FK", "article_id",                    False),
    ("",   "event_type",                    False),
    ("",   "event_location (JSONB)",        False),
    ("",   "matched_node (JSONB)",          False),   # NEW
    ("",   "event_date",                    False),
    ("",   "event_confidence",              False),
    ("",   "ml_risk_label",                 False),   # NEW
    ("",   "ml_risk_confidence",            False),   # NEW
    ("",   "sentiment_label",               False),   # NEW
    ("",   "sentiment_score",               False),   # NEW
    ("",   "predicted_disruption_prob",     False),   # NEW
    ("",   "predicted_impact_score",        False),   # NEW
])

# SUPPLIER_EVENT junction — moved down to clear DISRUPTION_EVENT
SUP_EVT = table("SE", "SUPPLIER_EVENT", 600, 720, [
    ("PK", "id",                True),
    ("FK", "event_id",          False),
    ("FK", "supplier_id",       False),
    ("",   "impact_severity",   False),
    ("",   "matched_entries",   False),
    ("",   "linked_at",         False),
])

# NEW: FORECAST_SNAPSHOT
FORE = table("FS", "FORECAST_SNAPSHOT", 960, 150, [
    ("PK", "snapshot_id",       True),
    ("FK", "supplier_id",       False),
    ("",   "forecast_date",     False),
    ("",   "day_offset",        False),
    ("",   "yhat",              False),
    ("",   "yhat_lower",        False),
    ("",   "yhat_upper",        False),
    ("",   "y_actual",          False),
    ("",   "method",            False),
])

# ── edges ─────────────────────────────────────────────────────────────────────
# Row IDs: table_id + "r" + row_index (0-based), port is the row cell itself

edges = [
    # SUPPLIER → RESILIENCEHISTORY  (1 to many)
    edge("e1",  "SUPr0",  "RESr0",  0.5, 1, 0.5, 0, "has"),
    # SUPPLIER → SUPPLYCHAIN_SUPPLIER
    edge("e2",  "SUPr0",  "SCSr0",  0.25, 1, 0.75, 0, "belongs to"),
    # SUPPLYCHAIN → SUPPLYCHAIN_SUPPLIER
    edge("e3",  "SCr0",   "SCSr0",  0.5, 1, 0.5, 0, "includes"),
    # NEWSARTICLE → DISRUPTION_EVENT
    edge("e4",  "ARTr0",  "EVTr0",  0.5, 1, 0.5, 0, "contains"),
    # DISRUPTION_EVENT → SUPPLIER_EVENT
    edge("e5",  "EVTr0",  "SEr0",   0.5, 1, 0.5, 0, "impacts"),
    # SUPPLIER → SUPPLIER_EVENT
    edge("e6",  "SUPr0",  "SEr0",   0.75, 1, 0.25, 0, "affected by"),
    # SUPPLIER → FORECAST_SNAPSHOT  (NEW)
    edge("e7",  "SUPr0",  "FSr0",   1, 0.5, 0, 0.5, "has forecast"),
]

# ── assemble ──────────────────────────────────────────────────────────────────
cells = "\n".join([
    SUPPLIER, NEWSARTICLE, SUPPLYCHAIN, SC_SUP, RESI, DISE, SUP_EVT, FORE,
    *edges,
])

xml = f"""<mxfile host="app.diagrams.net" version="29.3.2">
  <diagram name="ERD" id="updated-erd">
    <mxGraphModel dx="1200" dy="900" grid="1" gridSize="10" guides="1"
      tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1"
      pageWidth="1400" pageHeight="1100" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        {cells}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""

out = "/Users/meordanish/Desktop/Projects/SupplyChainForecast/docs/erd_updated.drawio"
with open(out, "w") as f:
    f.write(xml)
print(f"Saved: {out}")
