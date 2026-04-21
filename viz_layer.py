"""
viz layer - plotly chart builders for the dashboard.
each function takes a dataframe and a column name and returns a plotly figure.
dashboard.py calls these inside its callbacks.
"""

import pandas as pd
import plotly.express as px


def create_bar(df, col_name, top_n=10):
    """horizontal bar chart of the top N values in col_name"""
    counts = df[col_name].value_counts(dropna=False).head(top_n)
    # build a small df so plotly labels both axes correctly
    plot_df = pd.DataFrame({col_name: counts.index.astype(str), "count": counts.values})

    fig = px.bar(
        plot_df,
        x="count",
        y=col_name,
        orientation="h",
        title=f"Top {len(plot_df)} by {col_name}",
        text="count",
    )
    # sort biggest->smallest top to bottom
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    fig.update_traces(marker_color="#4c78a8")
    return fig


def create_pie(df, col_name):
    """pie chart. i use this for sponsor type because it's the headline
    chart and 'proportions of a whole' is what pie is good at"""
    counts = df[col_name].value_counts(dropna=False)
    plot_df = pd.DataFrame({col_name: counts.index.astype(str), "count": counts.values})
    fig = px.pie(
        plot_df,
        names=col_name,
        values="count",
        title=f"{col_name} breakdown",
        hole=0.3,  # donut looks cleaner than a solid pie imo
    )
    fig.update_traces(textinfo="percent+label")
    return fig


def create_ts(df, date_col):
    """time series - trial count per year"""
    series = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if series.empty:
        # if the filters leave no data, return an empty figure with a message
        fig = px.line(title="No data for the current filters")
        return fig

    yearly = series.dt.year.value_counts().sort_index()
    plot_df = pd.DataFrame({"year": yearly.index, "trials": yearly.values})
    fig = px.line(
        plot_df,
        x="year",
        y="trials",
        markers=True,
        title=f"Trials started per year (by {date_col})",
    )
    fig.update_traces(line_color="#e45756")
    return fig


def create_animation(df, date_col, group_col):
    """animated bar chart - cumulative trial count by group_col as the
    years tick forward. plotly's animation_frame does the work; the tricky
    part is building a long-format df that has one row per (year, group)
    with the CUMULATIVE count up to that year, so bars only grow."""
    work = df.dropna(subset=[date_col]).copy()
    work["year"] = pd.to_datetime(work[date_col], errors="coerce").dt.year
    work = work.dropna(subset=["year"])
    if work.empty:
        return px.bar(title="No data for the current filters")
    work["year"] = work["year"].astype(int)

    years = sorted(work["year"].unique())
    groups = sorted(work[group_col].dropna().astype(str).unique())

    # one row per (year, group). counts = trials started that year.
    per_year = (
        work.assign(**{group_col: work[group_col].astype(str)})
            .groupby(["year", group_col]).size()
            .unstack(fill_value=0)
            .reindex(index=years, columns=groups, fill_value=0)
            .cumsum()  # cumulative so bars grow monotonically
    )

    plot_df = per_year.reset_index().melt(id_vars="year", var_name=group_col, value_name="count")

    x_max = int(plot_df["count"].max()) if not plot_df.empty else 1
    fig = px.bar(
        plot_df,
        x="count",
        y=group_col,
        orientation="h",
        color=group_col,
        animation_frame="year",
        range_x=[0, x_max * 1.1 + 1],
        title=f"Cumulative trials by {group_col} over time (press play)",
        text="count",
    )
    fig.update_layout(
        yaxis={"categoryorder": "total ascending"},
        showlegend=False,
        transition={"duration": 300},
    )
    # slow the default frame speed so viewers can actually read each year
    if fig.layout.updatemenus:
        fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 600
        fig.layout.updatemenus[0].buttons[0].args[1]["transition"]["duration"] = 300
    return fig


def create_status_bar(df, col_name):
    """status bar chart. this is a separate function from create_bar because
    i wanted to color terminated/withdrawn/suspended in red so the failure
    bucket jumps out"""
    counts = df[col_name].value_counts(dropna=False)
    plot_df = pd.DataFrame({col_name: counts.index.astype(str), "count": counts.values})
    plot_df = plot_df.sort_values("count")

    def status_color(s):
        if s == "COMPLETED":
            return "#54a24b"  # green
        if s in ("TERMINATED", "WITHDRAWN", "SUSPENDED"):
            return "#e45756"  # red
        return "#b279a2"  # purple for everything else

    plot_df["color"] = plot_df[col_name].map(status_color)
    fig = px.bar(
        plot_df,
        x="count",
        y=col_name,
        orientation="h",
        title=f"Trials by {col_name}",
        text="count",
    )
    # px.bar doesn't take a per-bar color list directly, so i update_traces
    fig.update_traces(marker_color=plot_df["color"].tolist())
    return fig


if __name__ == "__main__":
    # smoke test. not trying to eyeball the actual charts here, just make
    # sure all 4 functions build a figure without crashing
    import data_layer as dl
    df = dl.clean_data(dl.load_data(dl.CSV_PATH))
    print("built pie:", create_pie(df, dl.SPONSOR_TYPE_COL).layout.title.text)
    print("built bar:", create_bar(df, dl.SPONSOR_KEY_COL).layout.title.text)
    print("built ts: ", create_ts(df, dl.START_DATE_COL).layout.title.text)
    print("built status bar:", create_status_bar(df, dl.STATUS_COL).layout.title.text)
