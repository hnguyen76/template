# HR Automation Template

Automation template for exporting a connected HR MySQL dataset to CSV and generating an HTML report.

## Files

- `HR_template.sql` joins HR tables through their primary and foreign keys.
- `run_monthly_hr_pipeline.ps1` exports the SQL result to `extracted_data/hr_employee_connected_extract_YYYYMMDDHHMM.csv` and generates the latest report.
- `generate_hr_report.py` reads the newest connected CSV and creates an HTML report with payroll comparison versus the previous extract.
- `setup_hr_mysql_credential.ps1` stores the MySQL credential locally using Windows DPAPI.
- `register_monthly_hr_task.ps1` registers a monthly Windows Task Scheduler job.

## First-Time Setup

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_hr_mysql_credential.ps1
```

## Run Manually

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_monthly_hr_pipeline.ps1
```

## Register Monthly Automation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\register_monthly_hr_task.ps1 -DayOfMonth 1 -Time 09:00
```

Generated CSV and report files are intentionally ignored by Git.

## Output Naming

- CSV extract: `hr_employee_connected_extract_YYYYMMDDHHMM.csv`
- HTML report: `hr_workforce_payroll_report_YYYYMMDDHHMM.html`

The timestamp is sortable and uses local run time.
