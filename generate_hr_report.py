from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from typing import Any


TIMESTAMP_IN_NAME = re.compile(r"(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})")
DASHED_DATE_IN_NAME = re.compile(r"(20\d{2}-\d{2}-\d{2})")
CONNECTED_EXTRACT_PREFIX = "hr_connected_"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a professional HR HTML report from the newest extracted CSV."
    )
    parser.add_argument(
        "--input-dir",
        default="extracted_data",
        help="Folder containing exported HR CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Folder where the report HTML file will be written.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Optional CSV path. If omitted, the newest dated CSV in input-dir is used.",
    )
    return parser.parse_args()


def extract_timestamp_from_name(path: Path) -> datetime | None:
    timestamp_match = TIMESTAMP_IN_NAME.search(path.name)
    if timestamp_match:
        return datetime.strptime("".join(timestamp_match.groups()), "%Y%m%d%H%M")

    date_match = DASHED_DATE_IN_NAME.search(path.name)
    if date_match:
        return datetime.strptime(date_match.group(1), "%Y-%m-%d")

    return None


def extract_score(path: Path) -> tuple[datetime, float]:
    file_timestamp = extract_timestamp_from_name(path) or datetime.min
    return file_timestamp, path.stat().st_mtime


def list_connected_extracts(input_dir: Path) -> list[Path]:
    csv_files = [
        path
        for path in input_dir.glob(f"{CONNECTED_EXTRACT_PREFIX}*.csv")
        if path.is_file()
    ]
    if not csv_files:
        raise FileNotFoundError(f"No connected HR CSV files found in {input_dir}")
    return sorted(csv_files, key=extract_score, reverse=True)


def find_latest_extract(input_dir: Path) -> Path:
    return list_connected_extracts(input_dir)[0]


def find_previous_extract(input_dir: Path, current_file: Path) -> Path | None:
    current = current_file.resolve()
    current_score = extract_score(current_file)
    for candidate in list_connected_extracts(input_dir):
        if candidate.resolve() == current:
            continue
        if extract_score(candidate) < current_score:
            return candidate
    return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def to_decimal(value: str | None) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def money(value: Decimal | int | float | None) -> str:
    if value is None:
        return "-"
    amount = Decimal(value).quantize(Decimal("0.01"))
    return f"${amount:,.2f}"


def number(value: int | Decimal | float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,}"


def avg(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def percent(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value.quantize(Decimal('0.1'))}%"


def delta_money(value: Decimal) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{money(value)}"


def delta_number(value: int) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{number(value)}"


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value))


def build_dataset(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    employees: dict[str, dict[str, Any]] = {}
    dependents_by_key: dict[tuple[str, str], dict[str, str]] = {}

    for row in rows:
        employee_id = row.get("employee_id", "").strip()
        if not employee_id:
            continue

        employee = employees.setdefault(employee_id, dict(row))
        for key, value in row.items():
            if value and not employee.get(key):
                employee[key] = value

        dependent_id = row.get("dependent_id", "").strip()
        if dependent_id:
            dependents_by_key[(employee_id, dependent_id)] = {
                "employee_id": employee_id,
                "dependent_id": dependent_id,
                "first_name": row.get("dependent_first_name", ""),
                "last_name": row.get("dependent_last_name", ""),
                "relationship": row.get("dependent_relationship", ""),
            }

    dependent_counts = Counter(employee_id for employee_id, _ in dependents_by_key)
    for employee in employees.values():
        employee["salary_decimal"] = to_decimal(employee.get("salary"))
        employee["min_salary_decimal"] = to_decimal(employee.get("min_salary"))
        employee["max_salary_decimal"] = to_decimal(employee.get("max_salary"))
        employee["dependent_count"] = dependent_counts[employee["employee_id"]]

    return list(employees.values()), list(dependents_by_key.values())


def group_employees(
    employees: list[dict[str, Any]],
    label_keys: tuple[str, ...],
    fallback: str = "Unassigned",
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for employee in employees:
        key = tuple(employee.get(label_key, "") or "" for label_key in label_keys)
        groups[key].append(employee)

    summaries: list[dict[str, Any]] = []
    for key, people in groups.items():
        label_values = [value for value in key if value]
        label = " / ".join(label_values) if label_values else fallback
        salaries = [person["salary_decimal"] for person in people if person["salary_decimal"] is not None]
        summaries.append(
            {
                "label": label,
                "key": key,
                "employee_count": len(people),
                "dependent_count": sum(int(person["dependent_count"]) for person in people),
                "total_salary": sum(salaries, Decimal("0")),
                "avg_salary": avg(salaries),
            }
        )

    return sorted(summaries, key=lambda item: (-item["employee_count"], item["label"]))


def payroll_total(employees: list[dict[str, Any]]) -> Decimal:
    return sum(
        (
            employee["salary_decimal"]
            for employee in employees
            if employee["salary_decimal"] is not None
        ),
        Decimal("0"),
    )


def payroll_comparison_by_group(
    current_employees: list[dict[str, Any]],
    previous_employees: list[dict[str, Any]],
    label_key: str,
    fallback: str = "Unassigned",
) -> list[dict[str, Any]]:
    current_summary = {
        item["label"]: item
        for item in group_employees(current_employees, (label_key,), fallback)
    }
    previous_summary = {
        item["label"]: item
        for item in group_employees(previous_employees, (label_key,), fallback)
    }

    rows: list[dict[str, Any]] = []
    for label in sorted(set(current_summary) | set(previous_summary)):
        current = current_summary.get(label, {})
        previous = previous_summary.get(label, {})
        current_payroll = current.get("total_salary", Decimal("0"))
        previous_payroll = previous.get("total_salary", Decimal("0"))
        delta = current_payroll - previous_payroll
        delta_pct = None
        if previous_payroll:
            delta_pct = (delta / previous_payroll) * Decimal("100")
        rows.append(
            {
                "label": label,
                "current_payroll": current_payroll,
                "previous_payroll": previous_payroll,
                "delta": delta,
                "delta_pct": delta_pct,
                "current_employees": current.get("employee_count", 0),
                "previous_employees": previous.get("employee_count", 0),
            }
        )

    return sorted(rows, key=lambda row: (abs(row["delta"]), row["label"]), reverse=True)


def salary_band_exceptions(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exceptions = []
    for employee in employees:
        salary = employee["salary_decimal"]
        min_salary = employee["min_salary_decimal"]
        max_salary = employee["max_salary_decimal"]
        if salary is None:
            continue
        if min_salary is not None and salary < min_salary:
            exceptions.append({**employee, "issue": "Below job minimum"})
        elif max_salary is not None and salary > max_salary:
            exceptions.append({**employee, "issue": "Above job maximum"})
    return exceptions


def table(headers: list[str], rows: list[list[str]], empty: str = "No rows") -> str:
    if not rows:
        return f'<p class="empty">{escape(empty)}</p>'

    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def bar(value: int, maximum: int) -> str:
    width = 0 if maximum <= 0 else round((value / maximum) * 100, 1)
    return (
        f'<span class="bar"><span style="width: {width}%"></span></span>'
        f'<span class="bar-label">{number(value)}</span>'
    )


def render_report(
    source_file: Path,
    output_file: Path,
    rows: list[dict[str, str]],
    employees: list[dict[str, Any]],
    dependents: list[dict[str, str]],
    report_timestamp: datetime,
    previous_source_file: Path | None = None,
    previous_employees: list[dict[str, Any]] | None = None,
) -> None:
    salaries = [employee["salary_decimal"] for employee in employees if employee["salary_decimal"] is not None]
    departments = {employee.get("department_id") for employee in employees if employee.get("department_id")}
    countries = {employee.get("country_id") for employee in employees if employee.get("country_id")}
    regions = {employee.get("region_id") for employee in employees if employee.get("region_id")}
    jobs = {employee.get("job_id") for employee in employees if employee.get("job_id")}
    exceptions = salary_band_exceptions(employees)

    department_summary = group_employees(employees, ("department_name",))
    job_summary = group_employees(employees, ("job_title",))
    region_summary = group_employees(employees, ("region_name",))
    country_summary = group_employees(employees, ("country_name",))

    max_department_count = max((item["employee_count"] for item in department_summary), default=0)
    max_job_count = max((item["employee_count"] for item in job_summary), default=0)
    max_region_count = max((item["employee_count"] for item in region_summary), default=0)

    manager_counts = Counter(
        employee.get("manager_full_name") or "No manager"
        for employee in employees
        if employee.get("manager_id")
    )
    dependent_relationships = Counter(
        dependent.get("relationship") or "Unspecified" for dependent in dependents
    )
    top_earners = sorted(
        employees,
        key=lambda employee: employee["salary_decimal"] or Decimal("0"),
        reverse=True,
    )[:10]

    largest_department = department_summary[0]["label"] if department_summary else "-"
    highest_avg_job = max(
        job_summary,
        key=lambda item: item["avg_salary"] or Decimal("0"),
        default={"label": "-", "avg_salary": None},
    )
    current_payroll = payroll_total(employees)

    payroll_comparison_html = (
        '<p class="empty">No previous connected HR extract was found for comparison.</p>'
    )
    if previous_source_file and previous_employees is not None:
        previous_timestamp = extract_timestamp_from_name(previous_source_file)
        previous_payroll = payroll_total(previous_employees)
        payroll_delta = current_payroll - previous_payroll
        payroll_delta_pct = None
        if previous_payroll:
            payroll_delta_pct = (payroll_delta / previous_payroll) * Decimal("100")

        comparison_rows = [
            [
                "<strong>Total Payroll</strong>",
                money(current_payroll),
                money(previous_payroll),
                f"<strong>{delta_money(payroll_delta)}</strong>",
                percent(payroll_delta_pct),
                number(len(employees)),
                number(len(previous_employees)),
                delta_number(len(employees) - len(previous_employees)),
            ]
        ]
        comparison_rows.extend(
            [
                [
                    safe_text(row["label"]),
                    money(row["current_payroll"]),
                    money(row["previous_payroll"]),
                    delta_money(row["delta"]),
                    percent(row["delta_pct"]),
                    number(row["current_employees"]),
                    number(row["previous_employees"]),
                    delta_number(row["current_employees"] - row["previous_employees"]),
                ]
                for row in payroll_comparison_by_group(
                    employees,
                    previous_employees,
                    "department_name",
                )
            ]
        )
        previous_display = (
            previous_timestamp.strftime("%Y-%m-%d %H:%M")
            if previous_timestamp
            else "unknown timestamp"
        )
        payroll_comparison_html = (
            f'<p class="meta">Compared against {safe_text(previous_source_file.name)} '
            f'({previous_display}).</p>'
            + table(
                [
                    "Scope",
                    "Current Payroll",
                    "Previous Payroll",
                    "Change",
                    "Change %",
                    "Current Employees",
                    "Previous Employees",
                    "Employee Change",
                ],
                comparison_rows,
            )
        )

    department_rows = [
        [
            safe_text(item["label"]),
            bar(item["employee_count"], max_department_count),
            money(item["avg_salary"]),
            money(item["total_salary"]),
            number(item["dependent_count"]),
        ]
        for item in department_summary
    ]

    job_rows = [
        [
            safe_text(item["label"]),
            bar(item["employee_count"], max_job_count),
            money(item["avg_salary"]),
            money(item["total_salary"]),
        ]
        for item in job_summary
    ]

    region_rows = [
        [
            safe_text(item["label"]),
            bar(item["employee_count"], max_region_count),
            money(item["avg_salary"]),
            money(item["total_salary"]),
        ]
        for item in region_summary
    ]

    country_rows = [
        [
            safe_text(item["label"]),
            number(item["employee_count"]),
            money(item["avg_salary"]),
            money(item["total_salary"]),
        ]
        for item in country_summary
    ]

    manager_rows = [
        [safe_text(manager), number(count)]
        for manager, count in manager_counts.most_common(10)
    ]

    dependent_rows = [
        [safe_text(relationship), number(count)]
        for relationship, count in dependent_relationships.most_common()
    ]

    top_earner_rows = [
        [
            safe_text(employee.get("employee_full_name")),
            safe_text(employee.get("job_title")),
            safe_text(employee.get("department_name")),
            money(employee["salary_decimal"]),
        ]
        for employee in top_earners
    ]

    exception_rows = [
        [
            safe_text(employee.get("employee_full_name")),
            safe_text(employee.get("job_title")),
            money(employee["salary_decimal"]),
            money(employee["min_salary_decimal"]),
            money(employee["max_salary_decimal"]),
            safe_text(employee["issue"]),
        ]
        for employee in exceptions
    ]

    missing_department = sum(1 for employee in employees if not employee.get("department_id"))
    missing_manager = sum(1 for employee in employees if not employee.get("manager_id"))
    missing_location = sum(1 for employee in employees if not employee.get("location_id"))

    report_display = report_timestamp.strftime("%Y-%m-%d %H:%M")

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HR Connected Dataset Report - {report_display}</title>
  <style>
    :root {{
      --ink: #17202a;
      --muted: #667085;
      --line: #d9e2ec;
      --band: #f5f7fa;
      --accent: #0f766e;
      --accent-2: #1d4ed8;
      --warn: #b45309;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #ffffff;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 28px 48px;
    }}
    header {{
      border-bottom: 3px solid var(--accent);
      padding-bottom: 18px;
      margin-bottom: 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 30px 0 12px;
      font-size: 20px;
      letter-spacing: 0;
    }}
    .meta {{
      color: var(--muted);
      font-size: 13px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin: 22px 0;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 14px 12px;
      background: var(--band);
    }}
    .card .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .card .value {{
      font-size: 24px;
      font-weight: 700;
      margin-top: 5px;
    }}
    .summary {{
      border-left: 4px solid var(--accent);
      background: #f0fdfa;
      padding: 14px 16px;
      margin: 18px 0 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 8px 0 18px;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      vertical-align: middle;
    }}
    th {{
      background: #eef2f7;
      color: #1f2937;
      font-weight: 700;
      position: sticky;
      top: 0;
    }}
    tr:nth-child(even) td {{ background: #fbfcfe; }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
    }}
    .bar {{
      display: inline-block;
      width: 130px;
      height: 9px;
      background: #e5e7eb;
      border-radius: 999px;
      overflow: hidden;
      vertical-align: middle;
      margin-right: 8px;
    }}
    .bar span {{
      display: block;
      height: 100%;
      background: var(--accent-2);
    }}
    .bar-label {{
      color: var(--ink);
      font-weight: 700;
    }}
    .empty {{
      color: var(--muted);
      font-style: italic;
    }}
    .quality {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .quality div {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }}
    .quality strong {{
      display: block;
      font-size: 22px;
      color: var(--warn);
    }}
    footer {{
      margin-top: 28px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }}
    @media print {{
      main {{ max-width: none; padding: 18px; }}
      .cards {{ grid-template-columns: repeat(3, 1fr); }}
      th {{ position: static; }}
    }}
    @media (max-width: 900px) {{
      .cards, .quality, .grid-2 {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 640px) {{
      main {{ padding: 22px 14px; }}
      .cards, .quality, .grid-2 {{ grid-template-columns: 1fr; }}
      table {{ font-size: 12px; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>HR Connected Dataset Report</h1>
    <div class="meta">
      Source: {safe_text(source_file.name)} | Extract timestamp: {report_display} |
      Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}
    </div>
  </header>

  <section class="cards">
    <div class="card"><div class="label">Employees</div><div class="value">{number(len(employees))}</div></div>
    <div class="card"><div class="label">Departments</div><div class="value">{number(len(departments))}</div></div>
    <div class="card"><div class="label">Jobs</div><div class="value">{number(len(jobs))}</div></div>
    <div class="card"><div class="label">Regions</div><div class="value">{number(len(regions))}</div></div>
    <div class="card"><div class="label">Dependents</div><div class="value">{number(len(dependents))}</div></div>
    <div class="card"><div class="label">Avg Salary</div><div class="value">{money(avg(salaries))}</div></div>
  </section>

  <section class="summary">
    <strong>Executive view.</strong>
    The latest extract contains {number(len(employees))} employees across {number(len(departments))} departments
    and {number(len(countries))} countries. Largest department: {safe_text(largest_department)}.
    Highest average-paying job group: {safe_text(highest_avg_job["label"])}
    ({money(highest_avg_job["avg_salary"])}). Total payroll in the extract is {money(current_payroll)}.
  </section>

  <h2>Payroll Change vs Previous Extract</h2>
  {payroll_comparison_html}

  <h2>Department Summary</h2>
  {table(["Department", "Employees", "Average Salary", "Payroll", "Dependents"], department_rows)}

  <h2>Job Summary</h2>
  {table(["Job Title", "Employees", "Average Salary", "Payroll"], job_rows)}

  <h2>Geography</h2>
  <div class="grid-2">
    <section>
      {table(["Region", "Employees", "Average Salary", "Payroll"], region_rows)}
    </section>
    <section>
      {table(["Country", "Employees", "Average Salary", "Payroll"], country_rows)}
    </section>
  </div>

  <h2>Leadership And Compensation</h2>
  <div class="grid-2">
    <section>
      <h2>Top Managers By Direct Reports</h2>
      {table(["Manager", "Direct Reports"], manager_rows)}
    </section>
    <section>
      <h2>Top Earners</h2>
      {table(["Employee", "Job", "Department", "Salary"], top_earner_rows)}
    </section>
  </div>

  <h2>Dependents</h2>
  {table(["Relationship", "Count"], dependent_rows)}

  <h2>Data Quality Checks</h2>
  <section class="quality">
    <div><strong>{number(missing_department)}</strong>Employees missing department</div>
    <div><strong>{number(missing_manager)}</strong>Employees missing manager</div>
    <div><strong>{number(missing_location)}</strong>Employees missing location</div>
    <div><strong>{number(len(exceptions))}</strong>Salary band exceptions</div>
  </section>

  <h2>Salary Band Exceptions</h2>
  {table(["Employee", "Job", "Salary", "Job Min", "Job Max", "Issue"], exception_rows, "No salary band exceptions detected.")}

  <footer>
    Report produced by generate_hr_report.py from {safe_text(source_file)}. Raw joined rows read: {number(len(rows))}.
  </footer>
</main>
</body>
</html>
"""

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    source_file = Path(args.source) if args.source else find_latest_extract(input_dir)
    if not source_file.exists():
        raise FileNotFoundError(f"Source CSV not found: {source_file}")

    rows = read_csv(source_file)
    if not rows:
        raise ValueError(f"Source CSV is empty: {source_file}")

    employees, dependents = build_dataset(rows)
    previous_source_file = None
    previous_employees = None
    try:
        previous_source_file = find_previous_extract(input_dir, source_file)
    except FileNotFoundError:
        previous_source_file = None
    if previous_source_file:
        previous_rows = read_csv(previous_source_file)
        previous_employees, _ = build_dataset(previous_rows)

    report_timestamp = extract_timestamp_from_name(source_file) or datetime.now()
    report_stamp = report_timestamp.strftime("%Y%m%d%H%M")
    output_file = Path(args.output_dir) / f"hr_report_{report_stamp}.html"
    render_report(
        source_file,
        output_file,
        rows,
        employees,
        dependents,
        report_timestamp,
        previous_source_file,
        previous_employees,
    )

    print(f"Source CSV: {source_file}")
    if previous_source_file:
        print(f"Previous CSV: {previous_source_file}")
    print(f"Report: {output_file}")
    print(f"Employees: {len(employees)}")
    print(f"Dependents: {len(dependents)}")


if __name__ == "__main__":
    main()
