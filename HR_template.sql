-- Active: 1776193943026@@127.0.0.1@3306@hr

USE hr;

-- HR connected dataset.
-- Grain: one row per employee/dependent combination.
-- If an employee has no dependent, the dependent_* columns are NULL.
--
-- Join keys:
--   employees.employee_id    -> dependents.employee_id
--   employees.job_id         -> jobs.job_id
--   employees.department_id  -> departments.department_id
--   employees.manager_id     -> employees.employee_id
--   departments.location_id  -> locations.location_id
--   locations.country_id     -> countries.country_id
--   countries.region_id      -> regions.region_id

SELECT
    e.employee_id,
    e.first_name AS employee_first_name,
    e.last_name AS employee_last_name,
    CONCAT_WS(' ', e.first_name, e.last_name) AS employee_full_name,
    e.email,
    e.phone_number,
    e.hire_date,
    e.salary,

    j.job_id,
    j.job_title,
    j.min_salary,
    j.max_salary,

    m.employee_id AS manager_id,
    m.first_name AS manager_first_name,
    m.last_name AS manager_last_name,
    CONCAT_WS(' ', m.first_name, m.last_name) AS manager_full_name,

    d.department_id,
    d.department_name,

    l.location_id,
    l.street_address,
    l.postal_code,
    l.city,
    l.state_province,

    c.country_id,
    c.country_name,

    r.region_id,
    r.region_name,

    dep.dependent_id,
    dep.first_name AS dependent_first_name,
    dep.last_name AS dependent_last_name,
    dep.relationship AS dependent_relationship
FROM employees AS e
LEFT JOIN jobs AS j
    ON j.job_id = e.job_id
LEFT JOIN employees AS m
    ON m.employee_id = e.manager_id
LEFT JOIN departments AS d
    ON d.department_id = e.department_id
LEFT JOIN locations AS l
    ON l.location_id = d.location_id
LEFT JOIN countries AS c
    ON c.country_id = l.country_id
LEFT JOIN regions AS r
    ON r.region_id = c.region_id
LEFT JOIN dependents AS dep
    ON dep.employee_id = e.employee_id
ORDER BY
    e.employee_id,
    dep.dependent_id;
