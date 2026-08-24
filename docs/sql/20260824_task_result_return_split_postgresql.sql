BEGIN;

ALTER TABLE public.t_param_task_results_return
    ADD COLUMN IF NOT EXISTS stock_code varchar(20),
    ADD COLUMN IF NOT EXISTS stock_name varchar(20),
    ADD COLUMN IF NOT EXISTS start_return_date date,
    ADD COLUMN IF NOT EXISTS end_return_date date,
    ADD COLUMN IF NOT EXISTS return_length integer;

ALTER TABLE public.t_param_task_results_return
    ALTER COLUMN stock_date TYPE text USING stock_date::text,
    ALTER COLUMN index_return TYPE text USING index_return::text,
    ALTER COLUMN start_return TYPE text USING start_return::text;

UPDATE public.t_param_task_results_return
SET
    stock_code = COALESCE(NULLIF(stock_code, ''), 'UNKNOWN'),
    stock_name = COALESCE(NULLIF(stock_name, ''), '未知股票'),
    stock_date = COALESCE(returns_json::jsonb -> 'dates', '[]'::jsonb)::text,
    index_return = COALESCE(returns_json::jsonb -> 'index_returns', '[]'::jsonb)::text,
    start_return = COALESCE(returns_json::jsonb -> 'start_returns', '[]'::jsonb)::text,
    return_length = jsonb_array_length(
        COALESCE(returns_json::jsonb -> 'dates', '[]'::jsonb)
    ),
    start_return_date = COALESCE(
        NULLIF((returns_json::jsonb -> 'dates' ->> 0), '')::date,
        DATE '1970-01-01'
    ),
    end_return_date = COALESCE(
        NULLIF((returns_json::jsonb -> 'dates' ->> (
            jsonb_array_length(COALESCE(returns_json::jsonb -> 'dates', '[]'::jsonb)) - 1
        )), '')::date,
        DATE '1970-01-01'
    );

ALTER TABLE public.t_param_task_results_return
    ALTER COLUMN stock_code SET NOT NULL,
    ALTER COLUMN stock_name SET NOT NULL,
    ALTER COLUMN start_return_date SET NOT NULL,
    ALTER COLUMN end_return_date SET NOT NULL,
    ALTER COLUMN return_length SET NOT NULL;

ALTER TABLE public.t_param_task_results_return
    DROP COLUMN IF EXISTS returns_json;

CREATE INDEX IF NOT EXISTS ix_task_results_return_stock_code
    ON public.t_param_task_results_return (stock_code);
CREATE INDEX IF NOT EXISTS ix_task_results_return_stock_name
    ON public.t_param_task_results_return (stock_name);

COMMENT ON COLUMN public.t_param_task_results_return.stock_code IS '股票代码';
COMMENT ON COLUMN public.t_param_task_results_return.stock_name IS '股票名称';
COMMENT ON COLUMN public.t_param_task_results_return.start_return_date IS '策略起始日期';
COMMENT ON COLUMN public.t_param_task_results_return.end_return_date IS '策略结束日期';
COMMENT ON COLUMN public.t_param_task_results_return.return_length IS '收益列长度';

COMMIT;
