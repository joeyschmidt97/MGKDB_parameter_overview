import marimo

__generated_with = "0.10.0"
app = marimo.App()


@app.cell
def __():
    import marimo as mo
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
    import query_parameters as qp
    return mo, os, qp, sys


@app.cell
def __(mo):
    mo.md("## MGKDB Parameter Sparsity Scan")
    return


@app.cell
def __(qp):
    lookup = qp.load_lookup(qp.LOOKUP_FILE)
    print(f"Loaded {len(lookup)} queryable parameters:")
    for e in lookup:
        print(f"  {e['parameter_name']:30s}  {e['db_field']}")
    return lookup,


@app.cell
def __(qp):
    from config.config_helper import Config
    from mgkdb.support.mgk_login import f_login_dbase

    config = Config()
    auth = config.get_path('MGKBD_AUTH')
    login = f_login_dbase(auth)
    database = login.connect()
    print("Connected to DB:", database.name)
    return Config, auth, config, database, f_login_dbase, login


@app.cell
def __(database, lookup, qp):
    import pandas as pd

    projection = {'gyrokineticsIMAS': 1, 'gyrokinetics': 1, 'Metadata.CodeTag': 1}
    rows = []
    for col_name in qp.COLLECTIONS:
        collection = getattr(database, col_name)
        print(f"{col_name}: {collection.count_documents({})} records")
        for record in collection.find({}, projection):
            row = qp.extract_params(record, lookup)
            row['collection'] = col_name
            rows.append(row)

    df = pd.DataFrame(rows)
    print(f"\nTotal records: {len(df)}")
    df
    return col_name, collection, df, pd, projection, record, row, rows


@app.cell
def __(df, mo):
    coverage = df.notna().mean().sort_values() * 100
    mo.md(f"""
    ## Parameter Coverage (% of records with value present)

    {coverage.to_frame('coverage_%').to_markdown()}
    """)
    return coverage,


@app.cell
def __(coverage):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6))
    coverage.plot.barh(ax=ax)
    ax.set_xlabel('Coverage (%)')
    ax.set_title('Parameter Sparsity')
    ax.axvline(50, color='red', linestyle='--', linewidth=0.8, label='50%')
    ax.legend()
    plt.tight_layout()
    fig
    return ax, fig, plt


if __name__ == "__main__":
    app.run()
