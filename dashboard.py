"""
dashboard.py - the app layer. uses panel to build the ui.

run with:  python dashboard.py

this is the third layer of the 3-layer dashboard pattern:
  data_layer.py  -> loading + filtering
  viz_layer.py   -> plotly chart builders
  dashboard.py   -> this file - widgets, layout, pn.bind wiring
"""

import panel as pn

import data_layer as dl
import viz_layer as vl


CARD_WIDTH = 320


def build_app():
    # load panel + the plotly extension. has to happen before any widgets
    # get created or panel won't know how to render plotly figures
    pn.extension("plotly")

    # load the csv once at startup. all the callbacks filter against this
    # in-memory df so filtering is instant
    df = dl.clean_data(dl.load_data(dl.CSV_PATH))

    # figure out the date range from the data so the date pickers start
    # at the full range
    earliest = df[dl.START_DATE_COL].dropna().min().date()
    latest = df[dl.START_DATE_COL].dropna().max().date()

    # ---- sidebar widgets ----
    start_date_picker = pn.widgets.DatePicker(
        name="Start date (>=)",
        value=earliest,
        start=earliest,
        end=latest,
    )
    end_date_picker = pn.widgets.DatePicker(
        name="End date (<=)",
        value=latest,
        start=earliest,
        end=latest,
    )

    # dropdowns. options come from the data_layer helper functions so
    # they're always in sync with whatever's actually in the data.
    # default is "All" = no filter on that field
    sponsor_type_select = pn.widgets.Select(
        name="Sponsor type",
        options=dl.get_sponsor_types(df),
        value="All",
    )
    phase_select = pn.widgets.Select(
        name="Phase",
        options=dl.get_phases(df),
        value="All",
    )
    status_select = pn.widgets.Select(
        name="Status",
        options=dl.get_statuses(df),
        value="All",
    )

    # ---- callbacks ----
    # each tab has a function that takes the 5 widget values and returns
    # a panel pane to display. pn.bind calls these on every widget change.

    def _filtered(start, end, sp, ph, st):
        """shared helper - apply the filters and return a subset"""
        return dl.filter_data(
            df,
            start_date=start,
            end_date=end,
            sponsor_type=sp,
            phase=ph,
            status=st,
        )

    def pie_view(start, end, sp, ph, st):
        filt = _filtered(start, end, sp, ph, st)
        if filt.empty:
            return pn.pane.Markdown("**No trials match these filters.**")
        # drop_duplicates on nct_id because otherwise multi-drug trials get
        # double-counted. (the master df has one row per trial-drug pair,
        # but when i'm counting trials i need one row per trial)
        fig = vl.create_pie(filt.drop_duplicates(dl.NCT_COL), dl.SPONSOR_TYPE_COL)
        return pn.pane.Plotly(fig, config={"responsive": True}, sizing_mode="stretch_width")

    def top_sponsors_view(start, end, sp, ph, st):
        filt = _filtered(start, end, sp, ph, st)
        if filt.empty:
            return pn.pane.Markdown("**No trials match these filters.**")
        fig = vl.create_bar(filt.drop_duplicates(dl.NCT_COL), dl.SPONSOR_KEY_COL)
        return pn.pane.Plotly(fig, config={"responsive": True}, sizing_mode="stretch_width")

    def phase_view(start, end, sp, ph, st):
        filt = _filtered(start, end, sp, ph, st)
        if filt.empty:
            return pn.pane.Markdown("**No trials match these filters.**")
        # top_n=6 because there are only 6 possible phase values
        fig = vl.create_bar(filt.drop_duplicates(dl.NCT_COL), dl.PHASE_COL, top_n=6)
        return pn.pane.Plotly(fig, config={"responsive": True}, sizing_mode="stretch_width")

    def status_view(start, end, sp, ph, st):
        filt = _filtered(start, end, sp, ph, st)
        if filt.empty:
            return pn.pane.Markdown("**No trials match these filters.**")
        fig = vl.create_status_bar(filt.drop_duplicates(dl.NCT_COL), dl.STATUS_COL)
        return pn.pane.Plotly(fig, config={"responsive": True}, sizing_mode="stretch_width")

    def timeseries_view(start, end, sp, ph, st):
        filt = _filtered(start, end, sp, ph, st)
        if filt.empty:
            return pn.pane.Markdown("**No trials match these filters.**")
        fig = vl.create_ts(filt.drop_duplicates(dl.NCT_COL), dl.START_DATE_COL)
        return pn.pane.Plotly(fig, config={"responsive": True}, sizing_mode="stretch_width")

    def animation_view(start, end, sp, ph, st):
        filt = _filtered(start, end, sp, ph, st)
        if filt.empty:
            return pn.pane.Markdown("**No trials match these filters.**")
        fig = vl.create_animation(
            filt.drop_duplicates(dl.NCT_COL), dl.START_DATE_COL, dl.SPONSOR_TYPE_COL
        )
        return pn.pane.Plotly(fig, config={"responsive": True}, sizing_mode="stretch_width")

    def table_view(start, end, sp, ph, st):
        filt = _filtered(start, end, sp, ph, st)
        if filt.empty:
            return pn.pane.Markdown("**No trials match these filters.**")
        # no drop_duplicates here - the table is supposed to show one row
        # per drug, not per trial
        cols = [
            dl.NCT_COL, dl.SPONSOR_COL, dl.SPONSOR_TYPE_COL, dl.DRUG_COL,
            dl.PHASE_COL, dl.STATUS_COL, dl.CONDITION_COL, dl.START_DATE_COL,
        ]
        return pn.widgets.DataFrame(
            filt[cols].reset_index(drop=True),
            name="Filtered trials",
            sizing_mode="stretch_width",
            height=500,
        )

    # ---- pn.bind ----
    # this is the magic of panel. pn.bind watches the widgets and re-runs
    # the callback any time one of them changes. no explicit event handlers.
    widgets = (start_date_picker, end_date_picker, sponsor_type_select, phase_select, status_select)
    pie_tab = pn.bind(pie_view, *widgets)
    top_tab = pn.bind(top_sponsors_view, *widgets)
    phase_tab = pn.bind(phase_view, *widgets)
    status_tab = pn.bind(status_view, *widgets)
    ts_tab = pn.bind(timeseries_view, *widgets)
    anim_tab = pn.bind(animation_view, *widgets)
    tbl_tab = pn.bind(table_view, *widgets)

    # ---- sidebar cards ----
    filter_card = pn.Card(
        pn.Column(
            start_date_picker,
            end_date_picker,
            sponsor_type_select,
            phase_select,
            status_select,
        ),
        title="Filters",
        width=CARD_WIDTH,
        collapsed=False,
    )

    info_card = pn.Card(
        pn.pane.Markdown(
            "### About\n"
            "This dashboard merges 500 oncology clinical trials from "
            "ClinicalTrials.gov with drug metadata from OpenFDA and a "
            "lookup file of 26 public pharma companies. Use the filters "
            "to drill into specific slices.\n\n"
            "**Note:** the `sponsor` field is whoever *ran* the trial, "
            "not whoever *paid for it*. Academic centers usually run "
            "trials funded by NIH grants or pharma contracts."
        ),
        title="About",
        width=CARD_WIDTH,
        collapsed=True,
    )

    # ---- main tabs ----
    # 6 tabs all reactive to the sidebar. tabs instead of one big page
    # because 6 charts stacked would be way too cramped
    tabs = pn.Tabs(
        ("Sponsor type", pie_tab),
        ("Top sponsors", top_tab),
        ("By phase", phase_tab),
        ("By status", status_tab),
        ("Over time", ts_tab),
        ("Animation", anim_tab),
        ("Trial table", tbl_tab),
        active=0,  # sponsor type opens by default - it's my headline chart
    )

    # ---- layout ----
    layout = pn.template.FastListTemplate(
        title="Oncology Clinical Trial Landscape",
        sidebar=[filter_card, info_card],
        theme_toggle=False,
        main=[tabs],
        header_background="#4c78a8",
    ).servable()

    return layout


# build the app on import so panel serve can find it
app = build_app()

if __name__ == "__main__":
    # only open the browser when running directly, not under panel serve
    app.show()
