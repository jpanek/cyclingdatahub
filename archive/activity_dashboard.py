# dash_app/activity_dashboard.py
import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from core.database import run_query_pd, run_query
from core.queries import (
    SQL_MONTHLY_ACTIVITY_METRICS, 
    SQL_GET_ACTIVITY_TYPES_BY_COUNT,
    SQL_GET_USER_NAME
)
from config import MY_ATHLETE_ID

def init_activity_dashboard(flask_app):
    dash_app = dash.Dash(
        server=flask_app,
        routes_pathname_prefix='/dashboard_dash/',
        external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP]
    )

    # Pre-fetch types for the dropdown
    types_df = run_query_pd(SQL_GET_ACTIVITY_TYPES_BY_COUNT, params=(MY_ATHLETE_ID,))
    all_types = types_df['type'].tolist() if not types_df.empty else []
    top_4_types = all_types[:4]

    # 1. Navbar Definition
    navbar = dbc.Navbar(
        dbc.Container([
            html.A(
                dbc.Row([
                    dbc.Col(html.Span("Cycling Stats", className="navbar-brand ms-2")),
                ], align="center", className="g-0"),
                href="/",
                style={"textDecoration": "none"},
            ),
            dbc.Nav([
                dbc.NavLink("Home", href="/", active="exact"),
                dbc.NavLink("Dashboard", href="/dashboard/", active="exact"),
            ], className="me-auto", navbar=True),
            html.Div([
                html.Strong(id="nav-user-name", className="text-white"),
                
            ], className="navbar-text d-flex align-items-center")
        ]),
        color="dark", dark=True, className="mb-4",
    )

    # 2. Layout Definition
    dash_app.layout = html.Div([
        navbar,
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H2("Performance Overview", className="fw-bold mb-0"),
                    html.P("Analyze your activity trends and metrics", className="text-muted"),
                ], width=12),
            ], className="mb-4"),

            dbc.Row([
                # Left Column: Filters
                dbc.Col([
                    html.Div([
                        html.Label("Activity Types", className="fw-bold mb-2"),
                        dbc.ButtonGroup([
                            dbc.Button("All", id="btn-all", color="light", size="sm", className="border"),
                            dbc.Button("Top 4", id="btn-top4", color="light", size="sm", className="border"),
                        ], className="w-100 mb-2"),
                        dcc.Dropdown(
                            id='activity-multiselect',
                            options=[{'label': t, 'value': t} for t in all_types],
                            value=top_4_types,
                            multi=True,
                            className="mb-4"
                        ),
                        html.Label("Metric", className="fw-bold mb-2"),
                        dbc.RadioItems(
                            id="metric-radio",
                            options=[
                                {"label": "Time (hrs)", "value": "duration_hours"},
                                {"label": "Distance (km)", "value": "distance_km"},
                                {"label": "Energy (kJ)", "value": "total_kj"},
                            ],
                            value="duration_hours",
                            className="mb-4 d-grid gap-2",
                            input_class_name="btn-check",
                            label_class_name="btn btn-outline-primary btn-sm",
                        ),
                        html.Label("History", className="fw-bold mb-2"),
                        dbc.Select(
                            id="horizon-select",
                            options=[
                                {"label": "Last 6 Months", "value": "6"},
                                {"label": "Last Year", "value": "12"},
                                {"label": "Last 2 Years", "value": "24"},
                                {"label": "All Time", "value": "999"},
                            ],
                            value="12",
                        ),
                    ], className="p-4 bg-white rounded-3 shadow-sm border")
                ], width=3),

                # Right Column: Data
                dbc.Col([
                    dbc.Row(id='metrics-cards', className="mb-4"),
                    dbc.Card([
                        dbc.CardHeader(id='chart-header', className="bg-white fw-bold py-3"),
                        dbc.CardBody([
                            dcc.Graph(id='activity-bar-chart', config={'displayModeBar': False})
                        ])
                    ], className="shadow-sm border-0 rounded-3")
                ], width=9)
            ])
        ], fluid=True, className="pb-5")
    ], style={'backgroundColor': '#f8f9fa', 'minHeight': '100vh'})

    # 3. Callbacks
    @dash_app.callback(
        Output("nav-user-name", "children"), 
        [Input("activity-multiselect", "id")] # Triggered on initial load
    )
    def update_navbar_info(_):
        user_data = run_query(SQL_GET_USER_NAME, (MY_ATHLETE_ID,))
        name = user_data[0]['firstname'] if user_data else "Athlete"
        return name

    @dash_app.callback(
        Output('activity-multiselect', 'value'),
        [Input('btn-all', 'n_clicks'), Input('btn-top4', 'n_clicks')],
        prevent_initial_call=True
    )
    def update_dropdown_selection(n_all, n_top4):
        ctx = callback_context
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        return all_types if button_id == 'btn-all' else top_4_types

    @dash_app.callback(
        [Output('metrics-cards', 'children'),
         Output('activity-bar-chart', 'figure'),
         Output('chart-header', 'children')],
        [Input('activity-multiselect', 'value'),
         Input('metric-radio', 'value'),
         Input('horizon-select', 'value')]
    )
    def update_viz(selected_types, selected_metric, horizon):
        raw_df = run_query_pd(SQL_MONTHLY_ACTIVITY_METRICS, params=(MY_ATHLETE_ID,))
        if raw_df.empty or not selected_types:
            return [], {}, "No Data"

        raw_df['month'] = pd.to_datetime(raw_df['month'])
        df = raw_df[raw_df['type'].isin(selected_types)].copy()

        if horizon != "999":
            cutoff = datetime.now() - relativedelta(months=int(horizon))
            df = df[df['month'] >= cutoff]

        card_style = "p-3 bg-white border-start border-primary border-4 rounded-3 shadow-sm h-100"
        metrics_html = [
            dbc.Col(html.Div([html.Div("Activities", className="small text-muted mb-1"), html.H4(f"{df['activities'].sum():,}", className="mb-0")], className=card_style), width=3),
            dbc.Col(html.Div([html.Div("Distance", className="small text-muted mb-1"), html.H4(f"{df['distance_km'].sum():,.0f} km", className="mb-0")], className=card_style), width=3),
            dbc.Col(html.Div([html.Div("Time", className="small text-muted mb-1"), html.H4(f"{df['duration_hours'].sum():,.0f} hrs", className="mb-0")], className=card_style), width=3),
            dbc.Col(html.Div([html.Div("Energy", className="small text-muted mb-1"), html.H4(f"{df['total_kj'].sum():,.0f} kJ", className="mb-0")], className=card_style), width=3),
        ]

        df['month_str'] = df['month'].dt.strftime('%b %Y')
        df = df.sort_values('month')

        fig = px.bar(
            df, x='month_str', y=selected_metric, color='type',
            template='plotly_white', barmode='stack',
            color_discrete_sequence=px.colors.qualitative.Prism
        )
        fig.update_layout(
            margin=dict(t=20, b=20, l=10, r=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=""),
            xaxis=dict(title="", showgrid=False),
            yaxis=dict(title="", gridcolor="#f0f0f0")
        )

        label = selected_metric.replace('_', ' ').title()
        return metrics_html, fig, f"Monthly {label}"

    return dash_app.server