def prep_csv(aggregates, params):
    '''
    Function that accepts the result of an aggregates function (see [./aggregates.py]) and the params object 
    used to construct that aggreagates and returns it in a tabular format (one of the params wil be used 
    as the headers.)
    - aggregates (object): an object returned by one of the aggregates functions from [./aggregates.py]
    - params (object): list of params used to construct the aggreagates objct
    '''
    #get list of each param and its values
    column_field = next((k for k, v in params.items() if v), None)
    column_field_choices = sorted({cell.get(column_field) for cell in aggregates.values()})

    # Dynamically extract all fields that are not 'count' or column_field
    fields = [f for f in list(aggregates.values())[0].keys() if f not in ['count', column_field]]
    row1 = fields + column_field_choices  # CSV header: breakdown fields + dynamic columns

    rows_map = {}
    for cell in aggregates.values():
        breakdowns = tuple(cell[k] for k in fields)  # Tuple of breakdown values in defined order
        column_field_value = cell.get(column_field)
        count = cell['count']

        #create dict for each breakdown
        if breakdowns not in rows_map:
            rows_map[breakdowns] = {}
        #add count
        rows_map[breakdowns][column_field_value] = count

    # Build final rows
    rows = [row1]
    for breakdown_values, counts_dict in rows_map.items():
        row = list(breakdown_values)
        for col_val in column_field_choices:
            row.append(counts_dict.get(col_val, 0))  # default to 0 if missing
        rows.append(row)

    return rows