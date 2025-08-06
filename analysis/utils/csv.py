def prep_csv(aggregates, params):
    column_field = next((k for k, v in params.items() if v), None)
    column_field_choices = sorted({cell[column_field] for cell in aggregates.values()})

    # Dynamically extract all fields that are not 'count' or column_field
    fields = [f for f in list(aggregates.values())[0].keys() if f not in ['count', column_field]]
    row1 = fields + column_field_choices  # CSV header: breakdown fields + dynamic columns

    rows_map = {}
    for cell in aggregates.values():
        breakdowns = tuple(cell[k] for k in fields)  # Tuple of breakdown values in defined order
        column_field_value = cell[column_field]
        count = cell['count']

        if breakdowns not in rows_map:
            rows_map[breakdowns] = {}

        rows_map[breakdowns][column_field_value] = count

    # Build final rows
    rows = [row1]
    for breakdown_values, counts_dict in rows_map.items():
        row = list(breakdown_values)
        for col_val in column_field_choices:
            row.append(counts_dict.get(col_val, 0))  # default to 0 if missing
        rows.append(row)

    return rows