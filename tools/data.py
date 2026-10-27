"""
Astra-Local Data Analysis Tools
Provides CSV/Excel ingestion, missing values detection, data cleaning,
chart plotting with matplotlib, and ML training with scikit-learn.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from config import DESKTOP_DIR


def _load_dataframe(file_path: str):
    """Helper to load a pandas DataFrame from CSV or Excel."""
    import pandas as pd
    path = Path(os.path.expandvars(file_path)).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path), path
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(path), path
    else:
        # Default try CSV
        return pd.read_csv(path), path


def data_inspect(file_path: str) -> Dict[str, Any]:
    """
    Loads a dataset (CSV/Excel) and inspects:
    - Shape (rows, columns)
    - Column data types
    - Missing values count and percentage per column
    - Summary statistics and top sample rows
    """
    try:
        import pandas as pd
        df, path = _load_dataframe(file_path)

        total_rows = len(df)
        missing_counts = df.isnull().sum()
        missing_report = {}
        for col, count in missing_counts.items():
            pct = round((count / total_rows) * 100, 2) if total_rows > 0 else 0
            missing_report[col] = {"missing_count": int(count), "missing_percent": pct}

        dtypes_report = {col: str(dtype) for col, dtype in df.dtypes.items()}
        num_df = df.describe().round(2)
        numeric_summary = num_df.where(pd.notnull(num_df), None).to_dict() if not df.select_dtypes(include="number").empty else {}
        sample_df = df.head(3)
        sample_records = sample_df.where(pd.notnull(sample_df), None).to_dict(orient="records")

        return {
            "success": True,
            "file": str(path),
            "rows": total_rows,
            "columns": list(df.columns),
            "dtypes": dtypes_report,
            "missing_values": missing_report,
            "has_missing": bool(df.isnull().values.any()),
            "summary_stats": numeric_summary,
            "sample_head": sample_records
        }
    except Exception as e:
        return {"success": False, "error": str(e), "file": file_path}


def data_clean(
    file_path: str,
    output_path: Optional[str] = None,
    drop_na: bool = False,
    fill_numeric: str = "mean",
    fill_categorical: str = "mode"
) -> Dict[str, Any]:
    """
    Cleans a dataset:
    - Drops or imputes missing values (mean/median/mode)
    - Removes duplicate rows
    - Trims whitespace from string columns
    - Saves cleaned dataset to output_path or <original>_cleaned.csv
    """
    try:
        import pandas as pd
        df, path = _load_dataframe(file_path)
        initial_rows = len(df)
        initial_missing = int(df.isnull().sum().sum())

        # Strip whitespace on text columns
        for col in df.select_dtypes(include=["object", "string"]).columns:
            df[col] = df[col].astype(str).str.strip()

        # Deduplicate
        df = df.drop_duplicates()
        deduped_rows = len(df)

        if drop_na:
            df = df.dropna()
        else:
            # Impute numeric
            for col in df.select_dtypes(include="number").columns:
                if df[col].isnull().any():
                    if fill_numeric == "median":
                        val = df[col].median()
                    elif fill_numeric == "zero":
                        val = 0
                    else:
                        val = df[col].mean()
                    df[col] = df[col].fillna(val)

            # Impute categorical
            for col in df.select_dtypes(include=["object", "string"]).columns:
                if df[col].isnull().any():
                    mode_val = df[col].mode()
                    val = mode_val[0] if not mode_val.empty else "Unknown"
                    df[col] = df[col].fillna(val)

        remaining_missing = int(df.isnull().sum().sum())

        if not output_path:
            out = path.parent / f"{path.stem}_cleaned.csv"
        else:
            out = Path(os.path.expandvars(output_path)).resolve()

        df.to_csv(out, index=False)

        return {
            "success": True,
            "original_file": str(path),
            "cleaned_file": str(out),
            "initial_rows": initial_rows,
            "final_rows": len(df),
            "duplicates_removed": initial_rows - deduped_rows,
            "missing_values_resolved": initial_missing - remaining_missing,
            "remaining_missing": remaining_missing
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def data_chart(
    file_path: str,
    chart_type: str = "bar",
    x_col: Optional[str] = None,
    y_col: Optional[str] = None,
    title: Optional[str] = None,
    output_image: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates a chart (bar, line, scatter, hist) from a dataset and saves as PNG.
    Default saves to user's Desktop.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd

        df, path = _load_dataframe(file_path)

        if not x_col:
            # Select first string or categorical column, else index
            str_cols = df.select_dtypes(include="object").columns
            x_col = str_cols[0] if len(str_cols) > 0 else df.columns[0]

        if not y_col:
            # Select first numeric column
            num_cols = df.select_dtypes(include="number").columns
            y_col = num_cols[0] if len(num_cols) > 0 else df.columns[-1]

        plt.figure(figsize=(10, 6))
        plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

        chart_type = chart_type.lower()
        if chart_type == "bar":
            # If multiple rows share x_col, aggregate by mean/sum
            agg_df = df.groupby(x_col)[y_col].sum().reset_index() if y_col in df.columns else df[x_col].value_counts().reset_index()
            plt.bar(agg_df.iloc[:, 0].astype(str), agg_df.iloc[:, 1], color="#4285F4", edgecolor="#1a73e8")
            plt.xticks(rotation=45, ha="right")
        elif chart_type == "line":
            plt.plot(df[x_col].astype(str), df[y_col], marker="o", color="#0F9D58", linewidth=2)
            plt.xticks(rotation=45, ha="right")
        elif chart_type == "scatter":
            plt.scatter(df[x_col], df[y_col], color="#EA4335", alpha=0.7)
        elif chart_type == "hist":
            plt.hist(df[y_col].dropna(), bins=15, color="#FBBC05", edgecolor="black")
        else:
            plt.bar(df[x_col].astype(str), df[y_col])

        plt.title(title or f"{chart_type.capitalize()} Chart: {y_col} by {x_col}", fontsize=14, fontweight="bold")
        plt.xlabel(x_col, fontsize=12)
        plt.ylabel(y_col, fontsize=12)
        plt.tight_layout()

        if not output_image:
            out_path = DESKTOP_DIR / f"{path.stem}_{chart_type}_chart.png"
        else:
            out_path = Path(os.path.expandvars(output_image)).resolve()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path, dpi=150)
        plt.close()

        return {
            "success": True,
            "chart_type": chart_type,
            "saved_image": str(out_path),
            "x_axis": x_col,
            "y_axis": y_col,
            "message": f"Chart successfully saved to {out_path}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def data_train_model(
    file_path: str,
    target_col: str,
    model_type: str = "auto"
) -> Dict[str, Any]:
    """
    Trains a machine learning model on the dataset using scikit-learn.
    Supports auto-detecting classification vs regression.
    """
    try:
        import pandas as pd
        from sklearn.model_selection import train_test_split
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.metrics import accuracy_score, r2_score, mean_squared_error

        df, path = _load_dataframe(file_path)
        if target_col not in df.columns:
            return {"success": False, "error": f"Target column '{target_col}' not found in data."}

        # Drop missing
        df_clean = df.dropna()

        # Separate X and y
        y = df_clean[target_col]
        X = df_clean.drop(columns=[target_col])

        # One-hot encode categorical features
        X = pd.get_dummies(X, drop_first=True)

        is_classification = model_type == "classification" or (
            model_type == "auto" and (y.dtype == "object" or y.nunique() <= 10)
        )

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        if is_classification:
            model = RandomForestClassifier(n_estimators=50, random_state=42)
            model.fit(X_train, y_train)
            preds = model.predict(X_test)
            acc = round(accuracy_score(y_test, preds), 4)
            return {
                "success": True,
                "model": "RandomForestClassifier",
                "accuracy": acc,
                "train_samples": len(X_train),
                "test_samples": len(X_test),
                "target": target_col,
                "message": f"Classification model trained with test accuracy: {acc * 100:.2f}%"
            }
        else:
            model = RandomForestRegressor(n_estimators=50, random_state=42)
            model.fit(X_train, y_train)
            preds = model.predict(X_test)
            r2 = round(r2_score(y_test, preds), 4)
            mse = round(mean_squared_error(y_test, preds), 4)
            return {
                "success": True,
                "model": "RandomForestRegressor",
                "r2_score": r2,
                "mse": mse,
                "train_samples": len(X_train),
                "test_samples": len(X_test),
                "target": target_col,
                "message": f"Regression model trained with R2 score: {r2}, MSE: {mse}"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
