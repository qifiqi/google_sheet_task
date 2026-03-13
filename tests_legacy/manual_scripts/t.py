import time

from app.utils.dfcf_api import DFCJStockApi


def _get_all_parameters(parameter, count_mode, end_date, start_date, market_type, date_range_mode, parameters):
    def _get_kline(klines, _year=None, _start_date_1=None, _end_date_1=None):
        # klines 里假设 'stock_date' 也是 'YYYY-MM-DD' 字符串
        if market_type == 'cn':
            if _year:
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k['stock_kp']}
                    for k in klines if int(k['stock_date'][:4]) == _year
                ]
            return [
                {'stock_date': k['stock_date'], 'stock_val': k['stock_kp']}
                for k in klines
                if _start_date_1 <= k['stock_date'] <= _end_date_1
            ]
        else:
            if _year:
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k['stock_sp']}
                    for k in klines if int(k['stock_date'][:4]) == _year
                ]
            return [
                {'stock_date': k['stock_date'], 'stock_val': k['stock_sp']}
                for k in klines
                if _start_date_1 <= k['stock_date'] <= _end_date_1
            ]

    dfcf_api = DFCJStockApi()
    stock_config = dfcf_api.get_search_list_by_stock_code(parameter, 10)
    if market_type == 'cn':
        stock_config = [i for i in stock_config if 'A' in i['securityTypeName']]
    else:
        stock_config = [i for i in stock_config if i['securityTypeName'] == '美股']

    if stock_config:
        stock_config = stock_config[0]

    market = stock_config['market']
    _end_year_1 = int(end_date[:4])
    now_time = time.strftime("%Y-%m-%d", time.localtime(time.time()))
    _end_year = int(now_time[:4])
    _start_date = int(start_date[:4])
    limit = (_end_year - _start_date + 1) * 250
    klines = dfcf_api.get_stock_kline_data(parameter, market, limit)
    all_kline = _get_kline(klines, _start_date_1=start_date, _end_date_1=end_date)
    data = [
    ]
    # for v1 in parameters[1]:
    #     for v2 in parameters[2]:
    #         data.append({'stock_code': parameter, 'kline': all_kline,"A1":v1,"B1":v2})
    #         if count_mode != 'n_plus_1':
    #             continue

    #         if 'recent' in date_range_mode:
    #             for i in range(1, (_end_year_1 - _start_date) + 1):
    #                 _i = i
    #                 if i!=0:
    #                     _i = i - 1

    #                 _end_data = f"{_end_year_1-_i}{end_date[4:]}"
    #                 _start_data = f"{_end_year_1 - i}{end_date[4:]}"
    #                 d = {"A1":v1,"B1":v2}
    #                 kline = _get_kline(klines, _start_data, _end_data)
    #                 if kline:
    #                     d['stock_code'] = parameter
    #                     d['kline'] = kline
    #                     data.append(d)

    #         if 'full' in date_range_mode:
    #             _all_kline = [ k for k in klines if start_date <= k['stock_date'] <= end_date]
    #             for i in range(_start_date, _end_year_1 + 1):
    #                 d = {"A1":v1,"B1":v2}
    #                 kline = _get_kline(_all_kline,_year=i)
    #                 if kline and len(kline) > 30:
    #                     d['stock_code'] = parameter
    #                     d['year'] = i
    #                     d['kline'] = kline
    #                     data.append(d)

    for i,v1 in enumerate(parameters[1]):
        for j,v2 in enumerate(parameters[2]):
            d = {'stock_code': parameter, "A1": v1, "B1": v2,'year':f'{_end_year}-{_start_date}'}
            if i ==0 and j ==0:
                d['kline']= all_kline
            data.append(d)

    if count_mode != 'n_plus_1':
        return data, len(all_kline) + 20

    if 'recent' in date_range_mode:
        for year in range(1, (_end_year_1 - _start_date) + 1):
            _year = year
            if year != 0:
                _year = year - 1

            _end_data = f"{_end_year_1 - _year}{end_date[4:]}"
            _start_data = f"{_end_year_1 - year}{end_date[4:]}"
            kline = _get_kline(klines, _start_date_1=_start_data, _end_date_1=_end_data)

            for i, v1 in enumerate(parameters[1]):
                for j, v2 in enumerate(parameters[2]):
                    d = {"A1": v1, "B1": v2, 'stock_code': parameter,'year': f'{_end_data[:4]}-{_start_data[:4]}'}
                    if i == 0 and j == 0:
                        if kline:
                            d['kline'] = kline
                    data.append(d)

    if 'full' in date_range_mode:
        _all_kline = [k for k in klines if start_date <= k['stock_date'] <= end_date]
        for year in range(_start_date, _end_year_1 + 1):
            kline = _get_kline(_all_kline, _year=year)

            for i, v1 in enumerate(parameters[1]):
                for j, v2 in enumerate(parameters[2]):
                    d = {"A1": v1, "B1": v2, 'stock_code': parameter, 'year': year}
                    if i == 0 and j == 0:
                        if kline and len(kline) > 30:
                            d['kline'] = kline
                        else:
                            continue
                    data.append(d)

    return data, len(all_kline) + 20

def main(combination,cache_parameters):
    column_A_length = 1000
    initial_results = {}
    c5_parameter_positions = ['A1','B1']
    results = {}
    cell_updates = {}
    c5_parameter_1 = f"xm:{combination[c5_parameter_positions[0]]}"
    c5_parameter_2 = f"ml:{combination[c5_parameter_positions[1]]}"
    cell_updates[c5_parameter_positions[0]] = c5_parameter_1
    cell_updates[c5_parameter_positions[1]] = c5_parameter_2

    def set_googl_val(initial_result_sleep=None):
        if 'kline' in combination:
            kline = combination['kline']
            for google_sheet in [1]:
                # A_num = google_sheet.get_last_row('A')
                _combination = cache_parameters['combination']
                if 'kline' in _combination:
                    _combination = _combination['kline']
                print(len(kline),len(_combination))
                if len(kline) != len(_combination):
                    A_num = column_A_length
                    print(f'当前A列行数: {A_num},{combination["A1"]},{combination["B1"]},{combination["stock_code"]},{combination.get("year")}准备滞空 A列 B列')
                    cache_parameters['combination'] = combination

            if initial_result_sleep:
                print(f'休眠{initial_result_sleep}秒 等待数据变动重新获取 initial_results')
                time.sleep(initial_result_sleep)

            # 准备要更新的单元格
            for i in range(len(kline)):
                item = {}
                if i <= len(kline):
                    item = kline[i]
                cell_num = i + 2
                cell_A = f"A{cell_num}"
                cell_B = f"B{cell_num}"
                stock_date = item.get('stock_date', "")
                stock_val = item.get('stock_val', "")
                cell_updates[cell_A] = stock_date
                cell_updates[cell_B] = stock_val


        for google_sheet in ['a']:
            print(f'长度：{len(cell_updates)} {combination["A1"]},{combination["B1"]},{combination["stock_code"]},{combination.get("year")}')

    set_googl_val()

if __name__ == '__main__':
    precomputed_params = []  # [(combinations, column_A_length)] 与 parameters[0] 对应
    cache_parameters = {'combination':[]}
    combinations, column_A_length = _get_all_parameters(
        '000001', 'n_plus_1', '2025-05-01', '2023-05-01', 'cn',
        ['full', 'recent'], [[], [1, 2], [1, 2]]
    )
    precomputed_params.append((combinations, column_A_length))

    for outer_idx, (combinations, column_A_length) in enumerate(precomputed_params):
        for combination in combinations:
            main(combination, cache_parameters)
