<template>
  <div
    v-loading="pageLoading"
    element-loading-text="请求中，请稍候..."
    class="app-page performance-analyzer-v2-page"
  >
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">绩效分析</div>
        <h2 class="page-title">V2：回测数据分析</h2>
      </div>
      <div class="page-toolbar__actions">
        <el-button @click="$router.push('/performance_analysis')">返回</el-button>
      </div>
    </div>

    <!-- 输入区：Google Sheet / 粘贴数据 / 导入 Excel / 参数配置 -->
    <el-card shadow="never" class="section-card">
      <div class="performance-analyzer-v2-input-head">
        <el-tabs v-model="activeSource" class="performance-analyzer-v2-source-tabs">
          <el-tab-pane label="Google Sheet" name="google">
            <el-row :gutter="12" align="middle">
              <el-col :xs="24" :lg="14">
                <el-input
                  v-model="gsUrl"
                  placeholder="Google Sheet URL：https://docs.google.com/spreadsheets/d/..."
                  :autocomplete="'off'"
                  @input="onUrlInput"
                  clearable
                />
                <div class="helper-text performance-analyzer-v2-meta">{{ gsMeta }}</div>
              </el-col>
              <el-col :xs="24" :lg="6">
                <el-select
                  v-model="sheetName"
                  :disabled="!worksheets.length"
                  :placeholder="worksheets.length ? '请选择工作表' : '工作表：请先输入 URL'"
                  class="full-width"
                >
                  <el-option v-for="w in worksheets" :key="w" :value="w" :label="w" />
                </el-select>
              </el-col>
              <el-col :xs="24" :lg="4">
                <el-button :loading="fetchingSheets" @click="fetchWorksheets()">获取</el-button>
              </el-col>
            </el-row>
          </el-tab-pane>

          <el-tab-pane label="粘贴数据" name="paste">
            <el-row :gutter="12">
              <el-col :xs="24" :lg="16">
                <el-input
                  v-model="pasteData"
                  type="textarea"
                  :rows="8"
                  class="performance-analyzer-v2-mono"
                  aria-label="回测收益数据"
                  placeholder="date&#9;index_return&#9;start_return&#10;2025-01-02&#9;0.0123&#9;0.0156&#10;2025-01-03&#9;-0.0081&#9;-0.0042"
                  @input="onPasteInput"
                />
              </el-col>
              <el-col :xs="24" :lg="8">
                <div class="performance-analyzer-v2-info-box">
                  <div class="performance-analyzer-v2-info-title">输入说明</div>
                  <div class="performance-analyzer-v2-info-subtitle">回测收益数据</div>
                  <div class="helper-text performance-analyzer-v2-paste-status">{{ pasteStatus }}</div>
                  <div class="helper-text">支持从 Excel 复制，列可由 Tab、逗号或空格分隔。首行如为列头会自动跳过。</div>
                </div>
              </el-col>
            </el-row>
          </el-tab-pane>

          <el-tab-pane label="导入 Excel" name="excel">
            <el-row :gutter="12">
              <el-col :xs="24" :lg="14">
                <div class="performance-analyzer-v2-upload-box">
                  <div class="performance-analyzer-v2-info-title">选择本地 Excel 文件</div>
                  <div class="helper-text">文件仅在当前浏览器中读取，不上传到服务器。</div>
                  <input ref="excelFileRef" type="file" accept=".xlsx,.xls" class="performance-analyzer-v2-file-input" @change="handleExcelImport" />
                  <el-button :loading="importingExcel" @click="excelFileRef?.click()">选择 Excel 文件</el-button>
                </div>
              </el-col>
              <el-col :xs="24" :lg="10">
                <div class="performance-analyzer-v2-info-box">
                  <div class="performance-analyzer-v2-info-title">导入规则</div>
                  <div class="performance-analyzer-v2-rule-row"><span>工作表</span><span>默认第 1 个工作表</span></div>
                  <div class="performance-analyzer-v2-rule-row"><span>数据范围</span><span>仅读取前三列（A:C）</span></div>
                  <div class="performance-analyzer-v2-rule-row"><span>首行处理</span><span>识别为列头时自动跳过</span></div>
                  <div class="performance-analyzer-v2-rule-row"><span>标准字段</span><span class="mono-inline">date / index_return / start_return</span></div>
                  <div class="helper-text performance-analyzer-v2-excel-status">{{ excelStatus }}</div>
                </div>
              </el-col>
            </el-row>
          </el-tab-pane>

          <el-tab-pane label="参数配置" name="config">
            <el-row :gutter="12">
              <el-col :xs="24" :lg="12">
                <div class="performance-analyzer-v2-config-item">
                  <div class="performance-analyzer-v2-config-label">市场下跌阶段阈值（指数月收益 &lt;）</div>
                  <el-input v-model="downturnThreshold" type="number" :step="0.1">
                    <template #append>%</template>
                  </el-input>
                  <div class="helper-text">七、极端行情表现 7.1 市场下跌阶段判定阈值，默认 -2%。</div>
                </div>
              </el-col>
              <el-col :xs="24" :lg="12">
                <div class="performance-analyzer-v2-config-item">
                  <div class="performance-analyzer-v2-config-label">市场上涨阶段阈值（指数月收益 &gt;）</div>
                  <el-input v-model="upturnThreshold" type="number" :step="0.1">
                    <template #append>%</template>
                  </el-input>
                  <div class="helper-text">七、极端行情表现 7.2 市场上涨阶段判定阈值，默认 2%。</div>
                </div>
              </el-col>
              <el-col :xs="24" :lg="12">
                <div class="performance-analyzer-v2-config-item">
                  <div class="performance-analyzer-v2-config-label">极端单日涨跌阈值（单日涨/跌 &gt;）</div>
                  <el-input v-model="dailyExtremeThreshold" type="number" :step="0.1">
                    <template #append>%</template>
                  </el-input>
                  <div class="helper-text">七、极端行情表现 7.3 涨幅/跌幅天数与涨跌比统计阈值，默认 2%。</div>
                </div>
              </el-col>
              <el-col :xs="24" :lg="12">
                <div class="performance-analyzer-v2-config-item">
                  <div class="performance-analyzer-v2-config-label">单日回撤统计阈值（单日跌幅 &lt;）</div>
                  <el-input v-model="dailyDrawdownThreshold" type="number" :step="0.1">
                    <template #append>%</template>
                  </el-input>
                  <div class="helper-text">二、风险类指标 回撤发生次数/频率统计阈值，默认 5%。</div>
                </div>
              </el-col>
              <el-col :xs="24" class="helper-text">
                修改后回到数据来源页签点击「分析」即可按新阈值重新计算；导出 Word 报告沿用本次分析的阈值。
              </el-col>
            </el-row>
          </el-tab-pane>
        </el-tabs>
        <el-button
          type="primary"
          class="performance-analyzer-v2-analyze-btn"
          :disabled="analyzeDisabled"
          :loading="analyzing"
          @click="runActiveAnalysis"
        >分析</el-button>
      </div>
    </el-card>

    <!-- 汇总卡片 -->
    <el-row :gutter="12" class="performance-analyzer-v2-summary-grid">
      <el-col :xs="12" :sm="6" class="performance-analyzer-v2-summary-grid__col">
        <el-card shadow="never" class="performance-analyzer-v2-summary-card performance-analyzer-v2-summary-card--primary">
          <div class="performance-analyzer-v2-summary-card__label">跑赢年份</div>
          <div class="performance-analyzer-v2-summary-card__value">{{ result ? fmtPct(result.outperform_year) : '-' }}</div>
          <div class="performance-analyzer-v2-summary-card__key">outperform_year</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-v2-summary-grid__col">
        <el-card shadow="never" class="performance-analyzer-v2-summary-card performance-analyzer-v2-summary-card--success">
          <div class="performance-analyzer-v2-summary-card__label">月超额波动率</div>
          <div class="performance-analyzer-v2-summary-card__value">{{ result ? fmtNum(result.monthly_excess_volatility, 4) : '-' }}</div>
          <div class="performance-analyzer-v2-summary-card__key">monthly_excess_volatility</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-v2-summary-grid__col">
        <el-card shadow="never" class="performance-analyzer-v2-summary-card performance-analyzer-v2-summary-card--warning">
          <div class="performance-analyzer-v2-summary-card__label">超额回撤胜率</div>
          <div class="performance-analyzer-v2-summary-card__value">{{ result ? fmtPct(result.excess_drawdown_winning_rate) : '-' }}</div>
          <div class="performance-analyzer-v2-summary-card__key">excess_drawdown_winning_rate</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-v2-summary-grid__col">
        <el-card shadow="never" class="performance-analyzer-v2-summary-card performance-analyzer-v2-summary-card--danger">
          <div class="performance-analyzer-v2-summary-card__label">年超额收益(整体)</div>
          <div class="performance-analyzer-v2-summary-card__value">{{ excessReturnsAll }}</div>
          <div class="performance-analyzer-v2-summary-card__key">excess_returns[all]</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-v2-summary-grid__col">
        <el-card shadow="never" class="performance-analyzer-v2-summary-card performance-analyzer-v2-summary-card--neutral">
          <div class="performance-analyzer-v2-summary-card__label">指数盈利年%</div>
          <div class="performance-analyzer-v2-summary-card__value">{{ result ? fmtPct(result.index_profit_annual) : '-' }}</div>
          <div class="performance-analyzer-v2-summary-card__key">index_profit_annual</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-v2-summary-grid__col">
        <el-card shadow="never" class="performance-analyzer-v2-summary-card performance-analyzer-v2-summary-card--neutral">
          <div class="performance-analyzer-v2-summary-card__label">模型盈利年%</div>
          <div class="performance-analyzer-v2-summary-card__value">{{ result ? fmtPct(result.start_profit_annual) : '-' }}</div>
          <div class="performance-analyzer-v2-summary-card__key">start_profit_annual</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-v2-summary-grid__col">
        <el-card shadow="never" class="performance-analyzer-v2-summary-card performance-analyzer-v2-summary-card--neutral">
          <div class="performance-analyzer-v2-summary-card__label">指数月波动率</div>
          <div class="performance-analyzer-v2-summary-card__value">{{ result ? fmtNum(result.index_monthly_return_volatility, 6) : '-' }}</div>
          <div class="performance-analyzer-v2-summary-card__key">index_monthly_return_volatility</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-v2-summary-grid__col">
        <el-card shadow="never" class="performance-analyzer-v2-summary-card performance-analyzer-v2-summary-card--neutral">
          <div class="performance-analyzer-v2-summary-card__label">模型月波动率</div>
          <div class="performance-analyzer-v2-summary-card__value">{{ result ? fmtNum(result.start_monthly_return_volatility, 6) : '-' }}</div>
          <div class="performance-analyzer-v2-summary-card__key">start_monthly_return_volatility</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 详情折叠 -->
    <el-card v-if="result" shadow="never" class="section-card">
      <div class="performance-analyzer-v2-detail-toolbar">
        <el-button size="small" @click="detailOpen = !detailOpen">
          {{ detailOpen ? '收起' : '展开' }} V2 数据明细
        </el-button>
        <div class="performance-analyzer-v2-detail-actions">
          <el-button size="small" type="primary" :loading="exportingExcel" @click="exportDetailsExcel">导出 Excel</el-button>
          <el-button size="small" type="success" :loading="exportingWord" @click="exportWordReport">导出 Word</el-button>
        </div>
      </div>
      <div v-if="detailOpen">
        <el-tabs v-model="activeDetailTab" tab-position="left">
          <el-tab-pane label="年度收益/回撤" name="annual">
            <el-row :gutter="12">
              <el-col :xs="24" :lg="12" class="performance-analyzer-v2-block-col">
                <div class="performance-analyzer-v2-block-title">年度收益率对比</div>
                <el-table :data="annualCompareRows" stripe size="small" border>
                  <el-table-column prop="year" label="Year" width="80" />
                  <el-table-column label="指数收益"><template #default="{row}"><span :class="colorClass(row.index_return)">{{ fmtPct(row.index_return) }}</span></template></el-table-column>
                  <el-table-column label="模型收益"><template #default="{row}"><span :class="colorClass(row.model_return)">{{ fmtPct(row.model_return) }}</span></template></el-table-column>
                  <el-table-column label="差值"><template #default="{row}"><span :class="colorClass(row.diff)">{{ row.diff === null ? '-' : fmtPct(row.diff) }}</span></template></el-table-column>
                </el-table>
              </el-col>
              <el-col :xs="24" :lg="12" class="performance-analyzer-v2-block-col">
                <div class="performance-analyzer-v2-block-title">年度最大回撤对比</div>
                <el-table :data="drawdownCompareRows" stripe size="small" border>
                  <el-table-column prop="year" label="Year" width="80" />
                  <el-table-column label="指数回撤"><template #default="{row}"><span class="text-danger">-{{ fmtPct(row.index_dd) }}</span></template></el-table-column>
                  <el-table-column label="模型回撤"><template #default="{row}"><span class="text-danger">-{{ fmtPct(row.model_dd) }}</span></template></el-table-column>
                  <el-table-column prop="dates" label="日期(指数/模型)" min-width="140" show-overflow-tooltip />
                </el-table>
              </el-col>
              <el-col :xs="24">
                <div class="performance-analyzer-v2-block-title">月超额收益百分比</div>
                <el-table :data="result.monthly_excess_return_percentage || []" stripe size="small" border>
                  <el-table-column prop="year" label="Year" width="80" />
                  <el-table-column label="月超额收益占比"><template #default="{row}">{{ fmtPct(row.excess_return) }}</template></el-table-column>
                </el-table>
              </el-col>
            </el-row>
          </el-tab-pane>

          <el-tab-pane label="超额收益" name="excess">
            <el-table :data="result.excess_returns || []" stripe size="small" border max-height="500">
              <el-table-column prop="year" label="Year" width="80" />
              <el-table-column label="模型年化"><template #default="{row}"><span :class="colorClass(row.start_annualized_return)">{{ fmtPct(row.start_annualized_return) }}</span></template></el-table-column>
              <el-table-column label="指数年化"><template #default="{row}"><span :class="colorClass(row.index_annualized_return)">{{ fmtPct(row.index_annualized_return) }}</span></template></el-table-column>
              <el-table-column label="超额"><template #default="{row}"><span :class="colorClass(row.annualized_return_diff)">{{ fmtPct(row.annualized_return_diff) }}</span></template></el-table-column>
              <el-table-column prop="start_end_date" label="区间" min-width="140" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="月超额收益" name="monthly_excess">
            <el-table :data="result.monthly_excess_returns || []" stripe size="small" border max-height="500">
              <el-table-column prop="year_month" label="年月" width="100" />
              <el-table-column label="指数月收益"><template #default="{row}"><span :class="colorClass(row.index_monthly_return)">{{ fmtPct(row.index_monthly_return) }}</span></template></el-table-column>
              <el-table-column label="模型月收益"><template #default="{row}"><span :class="colorClass(row.start_monthly_return)">{{ fmtPct(row.start_monthly_return) }}</span></template></el-table-column>
              <el-table-column label="超额差值"><template #default="{row}"><span :class="colorClass(row.monthly_excess_return_diff)">{{ fmtPct(row.monthly_excess_return_diff) }}</span></template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="卡玛比率" name="kama">
            <el-table :data="kamaRows" stripe size="small" border max-height="500">
              <el-table-column prop="year" label="年份" width="80" />
              <el-table-column label="指数卡玛比率"><template #default="{row}">{{ fmtNum(row.index_kama, 6) }}</template></el-table-column>
              <el-table-column label="模型卡玛比率"><template #default="{row}">{{ fmtNum(row.model_kama, 6) }}</template></el-table-column>
              <el-table-column label="指数年化"><template #default="{row}">{{ fmtPct(row.index_annual) }}</template></el-table-column>
              <el-table-column label="模型年化"><template #default="{row}">{{ fmtPct(row.model_annual) }}</template></el-table-column>
              <el-table-column label="指数回撤"><template #default="{row}">{{ fmtPct(row.index_dd) }}</template></el-table-column>
              <el-table-column label="模型回撤"><template #default="{row}">{{ fmtPct(row.model_dd) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="索提诺比例" name="sotino">
            <el-table :data="sotinoRows" stripe size="small" border max-height="500">
              <el-table-column prop="year" label="年份" width="80" />
              <el-table-column label="指数索提诺"><template #default="{row}">{{ fmtNum(row.index_sotino, 6) }}</template></el-table-column>
              <el-table-column label="模型索提诺"><template #default="{row}">{{ fmtNum(row.model_sotino, 6) }}</template></el-table-column>
              <el-table-column label="指数月均年化"><template #default="{row}">{{ fmtNum(row.index_avg_monthly, 6) }}</template></el-table-column>
              <el-table-column label="模型月均年化"><template #default="{row}">{{ fmtNum(row.model_avg_monthly, 6) }}</template></el-table-column>
              <el-table-column label="指数下行标准差"><template #default="{row}">{{ fmtNum(row.index_downside_std, 6) }}</template></el-table-column>
              <el-table-column label="模型下行标准差"><template #default="{row}">{{ fmtNum(row.model_downside_std, 6) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="夏普比率" name="sharpe">
            <el-table :data="sharpeRows" stripe size="small" border max-height="500">
              <el-table-column prop="period" label="区间" width="100" />
              <el-table-column label="指数夏普"><template #default="{row}">{{ fmtNum(row.index_sharpe, 6) }}</template></el-table-column>
              <el-table-column label="模型夏普"><template #default="{row}">{{ fmtNum(row.model_sharpe, 6) }}</template></el-table-column>
              <el-table-column label="指数平均月收益率"><template #default="{row}">{{ fmtPct(row.index_avg_monthly) }}</template></el-table-column>
              <el-table-column label="模型平均月收益率"><template #default="{row}">{{ fmtPct(row.model_avg_monthly) }}</template></el-table-column>
              <el-table-column label="指数月标准差"><template #default="{row}">{{ fmtPct(row.index_monthly_std) }}</template></el-table-column>
              <el-table-column label="模型月标准差"><template #default="{row}">{{ fmtPct(row.model_monthly_std) }}</template></el-table-column>
              <el-table-column label="指数年标准差"><template #default="{row}">{{ fmtPct(row.index_annual_std) }}</template></el-table-column>
              <el-table-column label="模型年标准差"><template #default="{row}">{{ fmtPct(row.model_annual_std) }}</template></el-table-column>
              <el-table-column prop="start_date" label="开始" width="100" show-overflow-tooltip />
              <el-table-column prop="end_date" label="结束" width="100" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="超额指标" name="excess_metrics">
            <el-table :data="excessMetricsRows" stripe size="small" border>
              <el-table-column prop="key" label="Key" width="220"><template #default="{row}"><code>{{ row.key }}</code></template></el-table-column>
              <el-table-column prop="value" label="Value" />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="回测修复天数" name="repair_days">
            <el-table :data="repairDaysRows" stripe size="small" border>
              <el-table-column prop="metric" label="Metric" width="160"><template #default="{row}"><code>{{ row.metric }}</code></template></el-table-column>
              <el-table-column label="Value"><template #default="{row}"><span :class="row.isExcess ? colorClass(row.value) : ''">{{ row.value }}</span></template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="盈利统计" name="profit">
            <el-row :gutter="12">
              <el-col :xs="24" :lg="12" class="performance-analyzer-v2-block-col">
                <div class="performance-analyzer-v2-block-title">盈利年百分比</div>
                <el-table :data="profitAnnualRow" stripe size="small" border>
                  <el-table-column label="指数"><template #default="{row}">{{ fmtPct(row.index) }}</template></el-table-column>
                  <el-table-column label="模型"><template #default="{row}">{{ fmtPct(row.model) }}</template></el-table-column>
                </el-table>
              </el-col>
              <el-col :xs="24" :lg="12">
                <el-row :gutter="12">
                  <el-col :xs="24" class="performance-analyzer-v2-block-col">
                    <div class="performance-analyzer-v2-block-title">指数盈利月占比</div>
                    <el-table :data="result.index_profit_monthly || []" stripe size="small" border max-height="200">
                      <el-table-column prop="year" label="Year" width="80" />
                      <el-table-column label="占比"><template #default="{row}">{{ fmtPct(row.profit_monthly_percentage) }}</template></el-table-column>
                    </el-table>
                  </el-col>
                  <el-col :xs="24">
                    <div class="performance-analyzer-v2-block-title">模型盈利月占比</div>
                    <el-table :data="result.start_profit_monthly || []" stripe size="small" border max-height="200">
                      <el-table-column prop="year" label="Year" width="80" />
                      <el-table-column label="占比"><template #default="{row}">{{ fmtPct(row.profit_monthly_percentage) }}</template></el-table-column>
                    </el-table>
                  </el-col>
                </el-row>
              </el-col>
            </el-row>
          </el-tab-pane>

          <el-tab-pane label="关键标量" name="scalars">
            <el-table :data="scalarsRows" stripe size="small" border max-height="500">
              <el-table-column prop="key" label="Key" width="280"><template #default="{row}"><code>{{ row.key }}</code></template></el-table-column>
              <el-table-column prop="name" label="Name" width="200" />
              <el-table-column prop="value" label="Value" />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="Sheet 结果" name="sheet_result">
            <el-table :data="sheetResultRows" stripe size="small" border max-height="500">
              <el-table-column prop="key" label="Key" width="220"><template #default="{row}"><code>{{ row.key }}</code></template></el-table-column>
              <el-table-column prop="value" label="Value" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="全量 JSON" name="raw">
            <div class="performance-analyzer-v2-raw-toolbar">
              <el-button size="small" @click="copyRawJson">复制</el-button>
            </div>
            <pre class="mono-pre performance-analyzer-v2-raw-json">{{ rawJsonText }}</pre>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-card>

    <!-- 图表区 -->
    <el-card v-if="result" shadow="never" class="section-card">
      <div class="performance-analyzer-v2-chart-title">V2 图表</div>
      <el-row :gutter="12">
        <el-col :xs="24" :lg="12" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">年度收益率（指数 vs 模型）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--320"><canvas ref="chartAnnualReturns"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">年超额收益（模型 - 指数）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--320"><canvas ref="chartExcessAnnual"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">年度最大回撤（指数 vs 模型）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--320"><canvas ref="chartAnnualDrawdown"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">卡玛比率（指数 vs 模型）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--320"><canvas ref="chartKama"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">索提诺比例（指数 vs 模型）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--320"><canvas ref="chartSotino"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">月收益率波动率（指数 vs 模型）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--320"><canvas ref="chartMonthlyVol"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">月超额收益（模型 - 指数）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--340"><canvas ref="chartMonthlyExcess"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">夏普比率对比（all / year_* / past_*）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--340"><canvas ref="chartSharpeCompare"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">超额指标（夏普 / 索提诺）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--320"><canvas ref="chartExcessMetrics"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">最大回测修复天数（含年度最大值）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--320"><canvas ref="chartRepairDays"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" class="performance-analyzer-v2-chart-col">
          <el-card shadow="never"><div class="performance-analyzer-v2-block-title">盈利月百分比（指数 vs 模型）</div><div class="performance-analyzer-v2-chart-box performance-analyzer-v2-chart-box--320"><canvas ref="chartProfitMonthly"></canvas></div></el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-empty v-if="!pageLoading && !result" description="输入 Google Sheet URL 或粘贴数据后点击分析" />

    <!-- Word 报告补充信息弹窗 -->
    <el-dialog v-model="wordDialogVisible" title="补充 Word 报告信息" width="480px" @open="resetWordDialog">
      <el-form label-position="top">
        <el-form-item label="股票">
          <el-select
            v-model="wordStockCode"
            class="full-width"
            filterable
            remote
            clearable
            :remote-method="searchWordExportStocks"
            :loading="stockSearching"
            :automatic-dropdown="true"
            placeholder="输入股票代码或名称搜索"
            @change="onWordStockChange"
          >
            <el-option
              v-for="item in stockResults"
              :key="item.code"
              :value="item.code"
              :label="`${item.code} · ${item.label || item.name || item.code}`"
            >
              <span class="performance-analyzer-v2-stock-code">{{ item.code }}</span>
              <span class="performance-analyzer-v2-stock-label">{{ item.label || item.name || '' }}</span>
            </el-option>
          </el-select>
          <div class="helper-text">请从内部股票查询结果中选择。</div>
        </el-form-item>
        <el-form-item label="价格类型">
          <el-select v-model="wordPriceType" class="full-width">
            <el-option v-for="(label, value) in WORD_PRICE_TYPE_LABELS" :key="value" :value="value" :label="label" />
          </el-select>
        </el-form-item>
      </el-form>
      <div class="helper-text">V2 单产品报告的权重固定为 100.00%。</div>
      <template #footer>
        <el-button @click="wordDialogVisible = false">取消</el-button>
        <el-button type="success" :loading="exportingWord" @click="confirmWordExport">导出 Word</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { analyzePerformanceAnalysisV1, analyzePerformanceAnalysis, exportPerformanceAnalysisResult, exportPerformanceAnalysisWordReport } from '@/api/performance_analysis'
import { getWorksheets } from '@/api/googleSheet'
import { searchStocks } from '@/api/backtest'
import { useChartJs } from '@/composables/useChartJs'

const { loadChartJs } = useChartJs()

// ── 常量 ─────────────────────────────────────────────────────
// 阈值输入按百分比填写并持久化（键名加 vue_ 前缀与静态版区分）
const RUNTIME_PARAMS_STORAGE_KEY = 'vue_v2_runtime_params'

const WORD_PRICE_TYPE_LABELS = {
  sp_price: '收盘价',
  kp_price: '开盘价',
  vwap_price: '加权平均价',
  ohlc_price: 'OHLC（开高低收）',
  random_price: '随机价',
}

const SCALAR_NAME_MAP = {
  outperform_year: '跑赢年份',
  monthly_excess_volatility: '月超额波动率',
  excess_drawdown_winning_rate: '超额回撤胜率',
  excess_sharpe: '超额夏普',
  excess_sortino: '超额索提诺',
  index_profit_annual: '指数盈利年百分比',
  start_profit_annual: '策略盈利年百分比',
  index_monthly_return_volatility: '指数月收益率波动率',
  start_monthly_return_volatility: '策略月收益率波动率',
  index_maximum_number_of_backtest_repair_days: '指数最大回测天数',
  start_maximum_number_of_backtest_repair_days: '策略最大回测天数',
  excess_maximum_number_of_backtest_repair_days: '超额最大回测天数',
  year_index_yearly_max_repair_days: '指数年最大回测修复天数',
  year_start_yearly_max_repair_days: '策略年最大回测修复天数',
}

const SCALAR_KEYS = [
  'outperform_year',
  'monthly_excess_volatility',
  'excess_drawdown_winning_rate',
  'excess_sharpe',
  'excess_sortino',
  'index_profit_annual',
  'start_profit_annual',
  'index_monthly_return_volatility',
  'start_monthly_return_volatility',
  'index_maximum_number_of_backtest_repair_days',
  'start_maximum_number_of_backtest_repair_days',
  'excess_maximum_number_of_backtest_repair_days',
]

// ── state ────────────────────────────────────────────────────
const activeSource = ref('google')
const activeDetailTab = ref('annual')
const detailOpen = ref(false)

const gsUrl = ref('')
const gsMeta = ref('')
const spreadsheetId = ref('')
const spreadsheetTitle = ref('')
const worksheets = ref([])
const sheetName = ref('')
const fetchingSheets = ref(false)

const pasteData = ref('')
const manualDataTitle = ref('')
const manualDataSheetName = ref('')
const excelFileRef = ref(null)
const excelStatus = ref('请选择 .xlsx 或 .xls 文件。')
const importingExcel = ref(false)

const downturnThreshold = ref('-2')
const upturnThreshold = ref('2')
const dailyExtremeThreshold = ref('2')
const dailyDrawdownThreshold = ref('5')

const analyzing = ref(false)
const exportingExcel = ref(false)
const exportingWord = ref(false)
const result = ref(null)
const lastSheetName = ref('')
const wordReportPayload = ref(null)

// Word 弹窗（股票搜索 + 价格类型）
const wordDialogVisible = ref(false)
const wordStockCode = ref('')
const wordStock = ref(null)
const wordPriceType = ref('sp_price')
const stockResults = ref([])
const stockSearching = ref(false)

const pageLoading = computed(() => analyzing.value || fetchingSheets.value)

// chart canvas refs
const chartAnnualReturns = ref(null)
const chartExcessAnnual = ref(null)
const chartAnnualDrawdown = ref(null)
const chartKama = ref(null)
const chartSotino = ref(null)
const chartMonthlyVol = ref(null)
const chartMonthlyExcess = ref(null)
const chartSharpeCompare = ref(null)
const chartExcessMetrics = ref(null)
const chartRepairDays = ref(null)
const chartProfitMonthly = ref(null)

const chartInstances = {}

// ── URL / 工作表 ─────────────────────────────────────────────
function extractSpreadsheetId(url) {
  if (!url) return ''
  const m1 = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/)
  if (m1 && m1[1]) return m1[1]
  const m2 = url.match(/[?&]id=([a-zA-Z0-9-_]+)/)
  if (m2 && m2[1]) return m2[1]
  return ''
}

function updateSpreadsheetMeta() {
  const url = gsUrl.value.trim()
  const id = extractSpreadsheetId(url)
  const changed = id !== spreadsheetId.value
  spreadsheetId.value = id
  if (!url) {
    gsMeta.value = ''
    return changed
  }
  if (!id) {
    gsMeta.value = '无法解析 spreadsheet_id'
    return changed
  }
  gsMeta.value = `spreadsheet_id: ${id}`
  return changed
}

function resetWorksheetSelect() {
  worksheets.value = []
  sheetName.value = ''
  spreadsheetTitle.value = ''
}

let urlDebounceTimer = null
function onUrlInput() {
  clearTimeout(urlDebounceTimer)
  urlDebounceTimer = setTimeout(() => {
    const changed = updateSpreadsheetMeta()
    if (changed) resetWorksheetSelect()
    autoFetchWorksheets()
  }, 500)
}

function autoFetchWorksheets() {
  const url = gsUrl.value.trim()
  if (!url || !spreadsheetId.value) return
  if (!worksheets.value.length) fetchWorksheets(true)
}

async function fetchWorksheets(silent = false) {
  const url = gsUrl.value.trim()
  if (!url || !spreadsheetId.value) {
    if (!silent) ElMessage.warning('请先输入正确的 Google Sheet URL（需要能解析 spreadsheet_id）')
    return
  }
  fetchingSheets.value = true
  try {
    // 拦截器已深解包：直接拿到 { worksheets, title } 载荷
    const data = await getWorksheets({ spreadsheet_id: spreadsheetId.value })
    worksheets.value = Array.isArray(data?.worksheets) ? data.worksheets : []
    spreadsheetTitle.value = data?.title || ''
    gsMeta.value = `spreadsheet_id: ${spreadsheetId.value}` + (spreadsheetTitle.value ? ` | 标题：${spreadsheetTitle.value}` : '')
    if (!worksheets.value.length) {
      sheetName.value = ''
      if (!silent) ElMessage.warning('未找到任何工作表')
      return
    }
    sheetName.value = worksheets.value[0]
    if (!silent) ElMessage.success('工作表已加载')
  } catch (error) {
    if (!silent) ElMessage.error('获取工作表失败：' + (error?.message || '未知错误'))
  } finally {
    fetchingSheets.value = false
  }
}

// ── 粘贴数据解析 ─────────────────────────────────────────────
function onPasteInput() {
  manualDataTitle.value = '手动数据'
  manualDataSheetName.value = '粘贴数据'
}

function prepareV2DataRows(text) {
  const rows = String(text).split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(/[\t,\s]+/).slice(0, 3))
  return prepareV2Rows(rows)
}

function prepareV2Rows(rows) {
  const dataRows = rows.filter((row) => row.some((cell) => String(cell ?? '').trim()))
  if (!dataRows.length) {
    throw new Error('请至少输入一行回测数据')
  }

  const hasHeader = isV2HeaderRow(dataRows[0])
  const usableRows = hasHeader ? dataRows.slice(1) : dataRows
  if (!usableRows.length) {
    throw new Error('列头后没有可分析的数据')
  }

  const normalizedRows = usableRows.map((row, index) => {
    const values = row.slice(0, 3).map((value) => String(value ?? '').trim())
    if (values.length < 3 || !isV2Date(values[0]) || !isV2Number(values[1]) || !isV2Number(values[2])) {
      throw new Error(`第 ${index + (hasHeader ? 2 : 1)} 行不是有效的日期、指数收益、模型收益数据`)
    }
    return values
  })

  return {
    text: normalizedRows.map((row) => row.join('\t')).join('\n'),
    rowCount: normalizedRows.length,
    hasHeader,
  }
}

function isV2HeaderRow(row) {
  const normalize = (value) => String(value ?? '').trim().toLowerCase().replace(/[\s_\-]/g, '')
  const headers = [
    new Set(['date', '日期', '时间', '交易日']),
    new Set(['indexreturn', '指数收益', '指数收益率']),
    new Set(['startreturn', '模型收益', '模型收益率', '策略收益', '策略收益率']),
  ]
  const values = row.slice(0, 3).map(normalize)
  if (values.every((value, index) => headers[index].has(value))) {
    return true
  }
  return !isV2Date(row[0]) && !isV2Number(row[1]) && !isV2Number(row[2])
}

function isV2Date(value) {
  const text = String(value ?? '').trim()
  if (!text) return false
  return !Number.isNaN(Date.parse(text))
}

function isV2Number(value) {
  const text = String(value ?? '').trim().replace(/%$/, '')
  return text !== '' && Number.isFinite(Number(text))
}

const pastePrepared = computed(() => {
  try {
    return { ok: true, prepared: prepareV2DataRows(pasteData.value) }
  } catch {
    return { ok: false, prepared: null }
  }
})

const pasteStatus = computed(() => {
  if (!pastePrepared.value.ok) return '需要三列：日期、指数收益、模型收益。'
  const { rowCount, hasHeader } = pastePrepared.value.prepared
  return `已识别 ${rowCount} 行有效数据${hasHeader ? '，已跳过列头' : ''}。`
})

// ── 参数配置（阈值）───────────────────────────────────────────
function parseThresholdInput(raw, fallback) {
  const text = String(raw ?? '').trim()
  if (text === '') return fallback
  const value = Number(text)
  return Number.isFinite(value) ? value : fallback
}

function collectRuntimeParams() {
  // 页面输入按百分比填写，payload 统一转换为小数阈值。
  return {
    market_downturn_threshold: parseThresholdInput(downturnThreshold.value, -2) / 100,
    market_upturn_threshold: parseThresholdInput(upturnThreshold.value, 2) / 100,
    daily_extreme_threshold: parseThresholdInput(dailyExtremeThreshold.value, 2) / 100,
    daily_drawdown_threshold: parseThresholdInput(dailyDrawdownThreshold.value, 5) / 100,
  }
}

function saveRuntimeParams() {
  try {
    localStorage.setItem(RUNTIME_PARAMS_STORAGE_KEY, JSON.stringify(collectRuntimeParams()))
  } catch {
    // localStorage 不可用（隐私模式等）时忽略，配置仅在当前页面生效。
  }
}

function restoreRuntimeParams() {
  let saved = null
  try {
    saved = JSON.parse(localStorage.getItem(RUNTIME_PARAMS_STORAGE_KEY) || 'null')
  } catch {
    saved = null
  }
  if (!saved || typeof saved !== 'object') return
  const toPct = (value) => String(Number((value * 100).toFixed(6)))
  if (Number.isFinite(saved.market_downturn_threshold)) downturnThreshold.value = toPct(saved.market_downturn_threshold)
  if (Number.isFinite(saved.market_upturn_threshold)) upturnThreshold.value = toPct(saved.market_upturn_threshold)
  if (Number.isFinite(saved.daily_extreme_threshold)) dailyExtremeThreshold.value = toPct(saved.daily_extreme_threshold)
  if (Number.isFinite(saved.daily_drawdown_threshold)) dailyDrawdownThreshold.value = toPct(saved.daily_drawdown_threshold)
}

// ── 分析入口 ─────────────────────────────────────────────────
const analyzeDisabled = computed(() => {
  if (activeSource.value === 'google') return worksheets.value.length === 0
  if (activeSource.value === 'paste') return !pastePrepared.value.ok
  // Excel 页签只负责导入，分析统一回粘贴页签执行
  return true
})

function runActiveAnalysis() {
  if (activeSource.value === 'google') return runAnalyzeGoogle()
  if (activeSource.value === 'paste') return runAnalyzePaste()
}

async function runAnalyzeGoogle() {
  const url = gsUrl.value.trim()
  if (!url) {
    ElMessage.warning('请输入 Google Sheet URL')
    return
  }
  if (!sheetName.value) {
    ElMessage.warning('请选择工作表')
    return
  }

  const runtimeParams = collectRuntimeParams()
  await requestAnalysis(
    analyzePerformanceAnalysisV1,
    {
      google_sheet_url: url,
      spreadsheet_id: spreadsheetId.value,
      google_sheet_name: sheetName.value,
      runtime_params: runtimeParams,
    },
    sheetName.value,
    spreadsheetTitle.value || 'Google Sheet',
    {
      report_type: 'RPT-S',
      google_sheet_url: url,
      spreadsheet_id: spreadsheetId.value,
      google_sheet_name: sheetName.value,
      metadata: { sheet_title: spreadsheetTitle.value },
      runtime_params: runtimeParams,
    },
  )
}

async function runAnalyzePaste() {
  let prepared
  try {
    prepared = prepareV2DataRows(pasteData.value)
  } catch (error) {
    ElMessage.warning(error?.message || '请输入有效的三列数据')
    return
  }

  pasteData.value = prepared.text
  const runtimeParams = collectRuntimeParams()
  await requestAnalysis(
    analyzePerformanceAnalysis,
    {
      data: prepared.text,
      time_format: 'auto',
      runtime_params: runtimeParams,
    },
    manualDataSheetName.value || '粘贴数据',
    manualDataTitle.value || '手动数据',
    {
      report_type: 'RPT-S',
      returns: prepared.text.split('\n').map((line) => {
        const [date, indexReturn, startReturn] = line.split('\t')
        return { date, index_return: Number(indexReturn), start_return: Number(startReturn) }
      }),
      metadata: { model_version: '单产品' },
      runtime_params: runtimeParams,
    },
  )
}

async function requestAnalysis(analyzeFn, body, sheetLabel, title, wordPayload) {
  analyzing.value = true
  try {
    // 拦截器已深解包：信封 data 为 { results, metrics }，results 才是指标本体
    const payload = await analyzeFn(body)
    const results = payload?.results ?? payload
    if (!results) {
      ElMessage.warning('后端未返回 results')
      return
    }

    result.value = results
    lastSheetName.value = sheetLabel
    spreadsheetTitle.value = title
    wordReportPayload.value = wordPayload
    ElMessage.success('V2 分析完成')
    await nextTick()
    renderCharts(results)
  } catch (error) {
    ElMessage.error('分析失败：' + (error?.message || '未知错误'))
  } finally {
    analyzing.value = false
  }
}

// ── Excel 导入 ───────────────────────────────────────────────
async function handleExcelImport(event) {
  const file = event.target.files[0]
  if (!file) return
  importingExcel.value = true
  try {
    const XLSX = await loadXlsx()
    excelStatus.value = '正在读取 Excel 文件...'
    const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array', cellDates: true })
    const firstSheetName = workbook.SheetNames[0]
    if (!firstSheetName) {
      throw new Error('Excel 中未找到工作表')
    }
    const worksheet = workbook.Sheets[firstSheetName]
    const rows = XLSX.utils.sheet_to_json(worksheet, { header: 1, defval: '', raw: true })
      .map((row) => [formatExcelDate(row[0], XLSX), row[1], row[2]])
    const prepared = prepareV2Rows(rows)
    pasteData.value = prepared.text
    manualDataTitle.value = file.name.replace(/\.[^.]+$/, '') || '本地 Excel'
    manualDataSheetName.value = firstSheetName
    excelStatus.value = `已读取“${firstSheetName}”的 ${prepared.rowCount} 行数据${prepared.hasHeader ? '，已跳过列头' : ''}。`
    activeSource.value = 'paste'
    ElMessage.success('Excel 已导入，请确认数据后分析')
  } catch (error) {
    excelStatus.value = `导入失败：${error?.message || '无法读取 Excel 文件'}`
  } finally {
    importingExcel.value = false
    event.target.value = ''
  }
}

function formatExcelDate(value, XLSX) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const pad = (n) => String(n).padStart(2, '0')
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
  }
  if (typeof value === 'number' && value > 20000 && value < 80000 && XLSX?.SSF?.parse_date_code) {
    const date = XLSX.SSF.parse_date_code(value)
    if (date) {
      const pad = (n) => String(n).padStart(2, '0')
      return `${date.y}-${pad(date.m)}-${pad(date.d)}`
    }
  }
  return value
}

// ── 格式化 ───────────────────────────────────────────────────
function fmtPct(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  return (Number(v) * 100).toFixed(digits) + '%'
}

function fmtNum(v, digits = 4) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  return Number(v).toFixed(digits)
}

function fmtInt(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  return String(Math.round(Number(v)))
}

function colorClass(v) {
  return (Number(v) || 0) >= 0 ? 'text-success' : 'text-danger'
}

function maxYearlyRepairDays(yearlyRepairDays) {
  if (!yearlyRepairDays || typeof yearlyRepairDays !== 'object' || Array.isArray(yearlyRepairDays)) {
    return null
  }
  const values = Object.values(yearlyRepairDays).map(Number).filter(Number.isFinite)
  return values.length ? Math.max(...values) : null
}

function idxByYear(list) {
  const m = new Map()
  if (Array.isArray(list)) {
    list.forEach((item) => {
      if (!item) return
      m.set(String(item.year), item)
    })
  }
  return m
}

function mergedYearRows(indexList, startList, mapRow) {
  const idx = idxByYear(indexList)
  const st = idxByYear(startList)
  const years = Array.from(new Set([...idx.keys(), ...st.keys()])).filter((y) => y !== 'all').sort()
  return years.map((y) => mapRow(y, idx.get(y), st.get(y)))
}

function formatSharpeKey(key) {
  const k = String(key ?? '')
  if (!k) return k
  if (k === 'all') return 'all'

  const mPast = k.match(/^past_(\d+)(?:_.*)?$/)
  if (mPast) {
    return `近${Number(mPast[1])}年`
  }

  const mYear = k.match(/^year_\d+_(\d{4})$/)
  if (mYear) {
    return mYear[1]
  }

  return k
}

// ── 明细表数据 ───────────────────────────────────────────────
const excessReturnsAll = computed(() => {
  if (!result.value) return '-'
  const all = Array.isArray(result.value.excess_returns)
    ? result.value.excess_returns.find((x) => String(x.year) === 'all')
    : null
  return all ? fmtPct(all.annualized_return_diff) : '-'
})

const annualCompareRows = computed(() => {
  if (!result.value) return []
  return mergedYearRows(result.value.index_returns_rate || [], result.value.start_returns_rate || [], (y, i, s) => {
    const a1 = i?.annual_return
    const a2 = s?.annual_return
    return { year: y, index_return: a1, model_return: a2, diff: (a2 !== undefined && a1 !== undefined) ? a2 - a1 : null }
  })
})

const drawdownCompareRows = computed(() => {
  if (!result.value) return []
  return mergedYearRows(result.value.index_maximum_drawdown?.year_maximum_drawdown || [], result.value.start_maximum_drawdown?.year_maximum_drawdown || [], (y, d1, d2) => ({
    year: y,
    index_dd: d1?.drawdown,
    model_dd: d2?.drawdown,
    dates: `${d1?.date || '-'} / ${d2?.date || '-'}`,
  }))
})

const kamaRows = computed(() => {
  if (!result.value) return []
  return mergedYearRows(result.value.index_kama_ratio || [], result.value.start_kama_ratio || [], (y, i, s) => ({
    year: y,
    index_kama: i?.kama_ratio,
    model_kama: s?.kama_ratio,
    index_annual: i?.annualized_return,
    model_annual: s?.annualized_return,
    index_dd: i?.drawdown,
    model_dd: s?.drawdown,
  }))
})

const sotinoRows = computed(() => {
  if (!result.value) return []
  return mergedYearRows(result.value.index_sortino_ratio || [], result.value.start_sortino_ratio || [], (y, i, s) => ({
    year: y,
    index_sotino: i?.sortino_ratio,
    model_sotino: s?.sortino_ratio,
    index_avg_monthly: i?.average_monthly_annualized_return,
    model_avg_monthly: s?.average_monthly_annualized_return,
    index_downside_std: i?.downside_standard_deviation,
    model_downside_std: s?.downside_standard_deviation,
  }))
})

const sharpeRows = computed(() => {
  if (!result.value) return []
  const idx = result.value.index_sharpe_ratios || {}
  const st = result.value.start_sharpe_ratios || {}
  const keys = Array.from(new Set([...Object.keys(idx), ...Object.keys(st)])).sort()
  return keys.flatMap((k) => {
    const i = idx[k]
    const s = st[k]
    const base = (i && typeof i === 'object') ? i : ((s && typeof s === 'object') ? s : null)
    if (!base) return []
    return [{
      period: formatSharpeKey(k),
      index_sharpe: i?.sharpe_ratio,
      model_sharpe: s?.sharpe_ratio,
      index_avg_monthly: i?.avg_monthly_return,
      model_avg_monthly: s?.avg_monthly_return,
      index_monthly_std: i?.monthly_std_dev,
      model_monthly_std: s?.monthly_std_dev,
      index_annual_std: i?.annual_std_dev,
      model_annual_std: s?.annual_std_dev,
      start_date: base?.start_date,
      end_date: base?.end_date,
    }]
  })
})

const excessMetricsRows = computed(() => {
  if (!result.value) return []
  return [
    { key: 'excess_sharpe', value: result.value.excess_sharpe === undefined ? '-' : fmtNum(result.value.excess_sharpe, 6) },
    { key: 'excess_sortino', value: result.value.excess_sortino === undefined ? '-' : fmtNum(result.value.excess_sortino, 6) },
  ]
})

const repairDaysRows = computed(() => {
  if (!result.value) return []
  return repairDaysValues(result.value).map(([metric, value]) => ({
    metric,
    value: fmtInt(value),
    // 静态版仅对 excess 行按正负着色
    isExcess: metric === 'excess',
  }))
})

const profitAnnualRow = computed(() => {
  if (!result.value) return []
  return [{ index: result.value.index_profit_annual, model: result.value.start_profit_annual }]
})

const scalarsRows = computed(() => {
  if (!result.value) return []
  const r = result.value
  const scalarValues = [
    ...SCALAR_KEYS.map((k) => [k, r[k]]),
    ['year_index_yearly_max_repair_days', maxYearlyRepairDays(r.year_index_yearly_max_repair_days)],
    ['year_start_yearly_max_repair_days', maxYearlyRepairDays(r.year_start_yearly_max_repair_days)],
  ]
  return scalarValues
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([k, value]) => {
      let v = value
      if (k.includes('profit_annual') || k.includes('outperform_year') || k.includes('winning_rate')) {
        v = fmtPct(v, 2)
      } else if (k.includes('repair_days')) {
        v = fmtInt(v)
      } else if (typeof v === 'number') {
        v = fmtNum(v, 6)
      }
      return { key: k, name: SCALAR_NAME_MAP[k] || '-', value: v }
    })
})

const sheetResultRows = computed(() => {
  const sheetResult = result.value?.sheet_result
  if (!sheetResult || typeof sheetResult !== 'object' || Array.isArray(sheetResult)) return []
  return Object.keys(sheetResult).sort().map((k) => ({
    key: k,
    value: typeof sheetResult[k] === 'object' ? JSON.stringify(sheetResult[k]) : String(sheetResult[k] ?? '-'),
  }))
})

const rawJsonText = computed(() => (result.value ? JSON.stringify(result.value, null, 2) : ''))

async function copyRawJson() {
  if (!rawJsonText.value) {
    ElMessage.warning('无可复制内容')
    return
  }
  try {
    await navigator.clipboard.writeText(rawJsonText.value)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

// ── 导出 Excel（后端 CSV → 前端 xlsx-js-style 套样式）─────────
async function exportDetailsExcel() {
  if (!result.value) {
    ElMessage.warning('请先完成分析再导出')
    return
  }
  exportingExcel.value = true
  try {
    const sanitize = (name) => String(name).replace(/[\\/:*?"<>|]/g, '_')
    const safeTitle = sanitize(spreadsheetTitle.value || 'v1')
    const safeSheet = sanitize(lastSheetName.value || 'sheet')
    const defaultFilename = `${safeTitle}_${safeSheet}_details.xlsx`
    const sourceFilename = `${safeTitle}_${safeSheet}_details.csv`

    // blob 拦截器返回 Blob 本体，这里是后端生成的 CSV 文本
    const blob = await exportPerformanceAnalysisResult({
      filename: sourceFilename,
      filename_title: safeTitle,
      analyze_result: result.value,
    })
    const XLSX = await loadXlsx()
    const workbook = XLSX.read(await blob.text(), { type: 'string' })
    const sheet = workbook.Sheets[workbook.SheetNames[0]]
    applyExportStyles(XLSX, sheet)
    XLSX.writeFile(workbook, defaultFilename, { compression: true })
    ElMessage.success(`文件已下载: ${defaultFilename}`)
  } catch (error) {
    ElMessage.error('导出失败：' + (error?.message || '未知错误'))
  } finally {
    exportingExcel.value = false
  }
}

function applyExportStyles(XLSX, sheet) {
  const border = {
    top: { style: 'thin', color: { rgb: 'D0D0D0' } },
    bottom: { style: 'thin', color: { rgb: 'D0D0D0' } },
    left: { style: 'thin', color: { rgb: 'D0D0D0' } },
    right: { style: 'thin', color: { rgb: 'D0D0D0' } },
  }
  const titleStyle = {
    font: { name: 'Microsoft YaHei', sz: 12, bold: true },
    fill: { fgColor: { rgb: 'F7E1A1' } },
    alignment: { horizontal: 'center', vertical: 'center' },
    border,
  }
  const headerStyle = {
    font: { name: 'Microsoft YaHei', sz: 11, bold: true },
    fill: { fgColor: { rgb: 'FCECC5' } },
    alignment: { horizontal: 'center', vertical: 'center' },
    border,
  }
  const firstColumnStyle = {
    font: { name: 'Microsoft YaHei', sz: 10, bold: true },
    fill: { fgColor: { rgb: 'F7E1A1' } },
    alignment: { horizontal: 'center', vertical: 'center' },
    border,
  }
  const bodyStyle = {
    font: { name: 'Microsoft YaHei', sz: 10 },
    alignment: { horizontal: 'center', vertical: 'center' },
    border,
  }
  const range = XLSX.utils.decode_range(sheet['!ref'] || 'A1:A1')

  for (let row = range.s.r; row <= range.e.r; row += 1) {
    for (let column = range.s.c; column <= range.e.c; column += 1) {
      const cell = sheet[XLSX.utils.encode_cell({ r: row, c: column })]
      if (!cell || cell.v === '') continue
      cell.s = bodyStyle
    }
  }

  for (let column = 0; column < 4; column += 1) {
    const cell = sheet[XLSX.utils.encode_cell({ r: 0, c: column })] || { t: 's', v: '' }
    cell.s = titleStyle
    sheet[XLSX.utils.encode_cell({ r: 0, c: column })] = cell
  }
  ;[2, 24, 30].forEach((row) => {
    for (let column = 0; column <= range.e.c; column += 1) {
      const cell = sheet[XLSX.utils.encode_cell({ r: row, c: column })]
      if (cell && cell.v !== '') cell.s = headerStyle
    }
  })
  for (let row = 3; row <= 23; row += 1) {
    const cell = sheet[XLSX.utils.encode_cell({ r: row, c: 0 })]
    if (cell && cell.v !== '') cell.s = firstColumnStyle
  }

  sheet['!cols'] = [
    { wch: 16 }, { wch: 28 }, { wch: 16 }, { wch: 18 },
    { wch: 4 }, { wch: 4 }, { wch: 4 }, { wch: 4 }, { wch: 4 },
    { wch: 16 }, { wch: 16 }, { wch: 16 },
  ]
  sheet['!freeze'] = { xSplit: 0, ySplit: 3, topLeftCell: 'A4', activePane: 'bottomLeft', state: 'frozen' }
}

// ── 导出 Word ────────────────────────────────────────────────
function exportWordReport() {
  if (!result.value || !wordReportPayload.value) {
    ElMessage.warning('请先完成分析再导出')
    return
  }

  // RPT-M 直接下载；V2 两种模式均产出 RPT-S，需要补充股票/价格类型
  if (wordReportPayload.value.report_type !== 'RPT-M') {
    wordDialogVisible.value = true
    return
  }
  downloadWordReport(wordReportPayload.value)
}

function resetWordDialog() {
  wordStockCode.value = ''
  wordStock.value = null
  stockResults.value = []
}

async function searchWordExportStocks(keyword) {
  const query = String(keyword ?? '').trim()
  if (!query) {
    stockResults.value = []
    return
  }
  stockSearching.value = true
  try {
    const data = await searchStocks({ q: query, page_size: 10 })
    stockResults.value = Array.isArray(data?.results) ? data.results : []
  } catch (error) {
    stockResults.value = []
    ElMessage.error(error?.message || '股票搜索失败')
  } finally {
    stockSearching.value = false
  }
}

function onWordStockChange(code) {
  const item = stockResults.value.find((x) => x.code === code)
  wordStock.value = item ? { code: item.code, name: item.name || item.label || item.code } : null
}

async function confirmWordExport() {
  if (!wordStock.value) {
    ElMessage.warning('请从搜索结果中选择股票')
    return
  }
  const payload = JSON.parse(JSON.stringify(wordReportPayload.value))
  payload.products = [{
    stock_code: wordStock.value.code,
    product_name: wordStock.value.name,
    ratio: '100.00%',
  }]
  payload.metadata = { ...(payload.metadata || {}), price_type: WORD_PRICE_TYPE_LABELS[wordPriceType.value] || '' }
  wordDialogVisible.value = false
  await downloadWordReport(payload)
}

async function downloadWordReport(payload) {
  exportingWord.value = true
  try {
    // blob 拦截器返回 Blob 本体（拿不到 Content-Disposition），沿用静态版默认文件名
    const blob = await exportPerformanceAnalysisWordReport(payload)
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = '策略回测绩效分析报告.docx'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(objectUrl)
    ElMessage.success('Word 报告已下载')
  } catch (error) {
    ElMessage.error('Word 导出失败：' + (error?.message || '未知错误'))
  } finally {
    exportingWord.value = false
  }
}

// ── xlsx-js-style CDN 动态加载（与 useChartJs 同模式）─────────
let xlsxPromise = null
function loadXlsx() {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('Excel 解析组件需要浏览器环境'))
  }
  if (window.XLSX) {
    return Promise.resolve(window.XLSX)
  }
  if (!xlsxPromise) {
    xlsxPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = 'https://cdn.jsdelivr.net/npm/xlsx-js-style@1.2.0/dist/xlsx.bundle.js'
      script.onload = () => resolve(window.XLSX)
      script.onerror = () => {
        xlsxPromise = null
        reject(new Error('Excel 解析组件加载失败'))
      }
      document.head.appendChild(script)
    })
  }
  return xlsxPromise
}

// ── 图表（Chart.js，轴/图例颜色随主题 CSS 变量取值）──────────
function chartTheme() {
  if (typeof window === 'undefined' || !window.getComputedStyle) {
    return { textColor: '#48658d', mutedColor: '#6c84a5', gridColor: 'rgba(30, 64, 175, 0.12)' }
  }
  const styles = getComputedStyle(document.documentElement)
  const read = (name, fallback) => (styles.getPropertyValue(name) || '').trim() || fallback
  return {
    textColor: read('--app-text-soft', '#48658d'),
    mutedColor: read('--app-text-muted', '#6c84a5'),
    gridColor: read('--app-border', 'rgba(30, 64, 175, 0.12)'),
  }
}

function baseChartOptions({ yTitle = null, xTitle = null, yOpts = {}, xOpts = {} } = {}) {
  const theme = chartTheme()
  const axis = (title, extra) => ({
    title: { display: Boolean(title), text: title || undefined, color: theme.mutedColor },
    ticks: { color: theme.textColor },
    grid: { color: theme.gridColor },
    ...extra,
  })
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { color: theme.textColor } } },
    scales: { x: axis(xTitle, xOpts), y: axis(yTitle, yOpts) },
  }
}

function destroyChart(key) {
  if (chartInstances[key]) {
    try {
      chartInstances[key].destroy()
    } catch {}
    chartInstances[key] = null
  }
}

function buildChart(Chart, canvasRef, key, type, labels, datasets, options = {}) {
  const el = canvasRef.value
  if (!el) return
  destroyChart(key)
  // options 由 baseChartOptions({...}) 生成，主题色在渲染时取 CSS 变量
  chartInstances[key] = new Chart(el, {
    type,
    data: { labels, datasets },
    options,
  })
}

function destroyAllCharts() {
  Object.keys(chartInstances).forEach(destroyChart)
}

function normYearSeries(list, valueKey) {
  const m = new Map()
  if (Array.isArray(list)) {
    list.forEach((x) => {
      if (!x || String(x.year) === 'all') return
      m.set(String(x.year), x[valueKey])
    })
  }
  const labels = Array.from(m.keys()).sort()
  return { labels, map: m }
}

function mergeYearLabels(...seriesList) {
  return Array.from(new Set(seriesList.flatMap((s) => s.labels))).sort()
}

function repairDaysValues(r) {
  return [
    ['index', r.index_maximum_number_of_backtest_repair_days],
    ['start', r.start_maximum_number_of_backtest_repair_days],
    ['excess', r.excess_maximum_number_of_backtest_repair_days],
    ['year_index_max', maxYearlyRepairDays(r.year_index_yearly_max_repair_days)],
    ['year_start_max', maxYearlyRepairDays(r.year_start_yearly_max_repair_days)],
  ].filter(([, value]) => value !== undefined && value !== null && !Number.isNaN(Number(value)))
}

function sharpeEntriesToSeries(obj) {
  const arr = []
  if (!obj || typeof obj !== 'object') return arr
  Object.entries(obj).forEach(([k, v]) => {
    if (!v || typeof v !== 'object') return
    if (v.sharpe_ratio === undefined || v.sharpe_ratio === null) return
    arr.push({ key: formatSharpeKey(k), sharpe: v.sharpe_ratio })
  })
  return arr
}

async function renderCharts(r) {
  let Chart
  try {
    Chart = await loadChartJs()
  } catch {
    return
  }

  // 1. 年度收益率（指数 vs 模型）
  const idxA = normYearSeries(r.index_returns_rate, 'annual_return')
  const stA = normYearSeries(r.start_returns_rate, 'annual_return')
  const labA = mergeYearLabels(idxA, stA)
  buildChart(Chart, chartAnnualReturns, 'annualReturns', 'line', labA, [
    { label: '指数年度收益(%)', data: labA.map((y) => idxA.map.get(y) ?? null).map((v) => v === null ? null : v * 100), borderColor: '#0d6efd', backgroundColor: 'rgba(13,110,253,0.08)', tension: 0.1, fill: true },
    { label: '模型年度收益(%)', data: labA.map((y) => stA.map.get(y) ?? null).map((v) => v === null ? null : v * 100), borderColor: '#198754', backgroundColor: 'rgba(25,135,84,0.08)', tension: 0.1, fill: true },
  ], baseChartOptions({ yTitle: 'Return (%)', xTitle: 'Year' }))

  // 2. 年超额收益（模型 - 指数）
  const exMap = new Map()
  if (Array.isArray(r.excess_returns)) {
    r.excess_returns.forEach((x) => {
      if (!x || String(x.year) === 'all') return
      exMap.set(String(x.year), x.annualized_return_diff)
    })
  }
  const exLabels = Array.from(exMap.keys()).sort()
  const exVals = exLabels.map((y) => (exMap.get(y) ?? 0) * 100)
  buildChart(Chart, chartExcessAnnual, 'excessAnnual', 'bar', exLabels, [
    { label: '年超额收益(%)', data: exVals, backgroundColor: exVals.map((v) => v >= 0 ? 'rgba(25,135,84,0.5)' : 'rgba(220,53,69,0.5)'), borderColor: exVals.map((v) => v >= 0 ? '#198754' : '#dc3545'), borderWidth: 1 },
  ], baseChartOptions({ yTitle: 'Excess Return (%)' }))

  // 3. 年度最大回撤（指数 vs 模型）
  const idxD = normYearSeries(r.index_maximum_drawdown?.year_maximum_drawdown, 'drawdown')
  const stD = normYearSeries(r.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown')
  const labD = mergeYearLabels(idxD, stD)
  buildChart(Chart, chartAnnualDrawdown, 'annualDrawdown', 'line', labD, [
    { label: '指数最大回撤(%)', data: labD.map((y) => idxD.map.get(y) ?? null).map((v) => v === null ? null : v * 100), borderColor: '#dc3545', backgroundColor: 'rgba(220,53,69,0.08)', tension: 0.1, fill: true },
    { label: '模型最大回撤(%)', data: labD.map((y) => stD.map.get(y) ?? null).map((v) => v === null ? null : v * 100), borderColor: '#fd7e14', backgroundColor: 'rgba(253,126,20,0.08)', tension: 0.1, fill: true },
  ], baseChartOptions({ yTitle: 'Drawdown (%)', xTitle: 'Year' }))

  // 4. 卡玛比率（指数 vs 模型）
  const idxK = normYearSeries(r.index_kama_ratio, 'kama_ratio')
  const stK = normYearSeries(r.start_kama_ratio, 'kama_ratio')
  const labK = mergeYearLabels(idxK, stK)
  buildChart(Chart, chartKama, 'kama', 'line', labK, [
    { label: '指数Kama', data: labK.map((y) => idxK.map.get(y) ?? null), borderColor: '#0dcaf0', backgroundColor: 'rgba(13,202,240,0.08)', tension: 0.1, fill: true },
    { label: '模型Kama', data: labK.map((y) => stK.map.get(y) ?? null), borderColor: '#6610f2', backgroundColor: 'rgba(102,16,242,0.08)', tension: 0.1, fill: true },
  ], baseChartOptions({ yTitle: 'Kama Ratio', xTitle: 'Year' }))

  // 5. 索提诺比例（指数 vs 模型）
  const idxS = normYearSeries(r.index_sortino_ratio, 'sortino_ratio')
  const stS = normYearSeries(r.start_sortino_ratio, 'sortino_ratio')
  const labS = mergeYearLabels(idxS, stS)
  buildChart(Chart, chartSotino, 'sotino', 'line', labS, [
    { label: '指数Sotino', data: labS.map((y) => idxS.map.get(y) ?? null), borderColor: '#20c997', backgroundColor: 'rgba(32,201,151,0.08)', tension: 0.1, fill: true },
    { label: '模型Sotino', data: labS.map((y) => stS.map.get(y) ?? null), borderColor: '#d63384', backgroundColor: 'rgba(214,51,132,0.08)', tension: 0.1, fill: true },
  ], baseChartOptions({ yTitle: 'Sotino Ratio', xTitle: 'Year' }))

  // 6. 月收益率波动率（指数 vs 模型）
  buildChart(Chart, chartMonthlyVol, 'monthlyVol', 'bar', ['指数', '模型'], [
    { label: '月收益率波动率', data: [r.index_monthly_return_volatility ?? null, r.start_monthly_return_volatility ?? null], backgroundColor: ['rgba(13,110,253,0.5)', 'rgba(25,135,84,0.5)'], borderColor: ['#0d6efd', '#198754'], borderWidth: 1 },
  ], baseChartOptions({ yTitle: 'Volatility' }))

  // 7. 月超额收益（模型 - 指数）
  const mer = Array.isArray(r.monthly_excess_returns)
    ? r.monthly_excess_returns.filter((x) => x?.year_month).sort((a, b) => String(a.year_month).localeCompare(String(b.year_month)))
    : []
  const merLabels = mer.map((x) => String(x.year_month))
  const merVals = mer.map((x) => (x.monthly_excess_return_diff ?? null) === null ? null : Number(x.monthly_excess_return_diff) * 100)
  buildChart(Chart, chartMonthlyExcess, 'monthlyExcessReturns', 'bar', merLabels, [
    { label: '月超额收益(%)', data: merVals, backgroundColor: merVals.map((v) => (v ?? 0) >= 0 ? 'rgba(25,135,84,0.55)' : 'rgba(220,53,69,0.55)'), borderColor: merVals.map((v) => (v ?? 0) >= 0 ? '#198754' : '#dc3545'), borderWidth: 1 },
  ], baseChartOptions({ yTitle: 'Excess Return (%)', xOpts: { ticks: { autoSkip: true, maxRotation: 60, minRotation: 0 } } }))

  // 8. 夏普比率对比（all / year_* / past_*）
  const idxSh = sharpeEntriesToSeries(r.index_sharpe_ratios)
  const stSh = sharpeEntriesToSeries(r.start_sharpe_ratios)
  const shLabels = Array.from(new Set([...idxSh.map((x) => x.key), ...stSh.map((x) => x.key)])).sort((a, b) => {
    if (a === 'all' && b !== 'all') return -1
    if (b === 'all' && a !== 'all') return 1
    return String(a).localeCompare(String(b))
  })
  const idxShMap = new Map(idxSh.map((x) => [x.key, x.sharpe]))
  const stShMap = new Map(stSh.map((x) => [x.key, x.sharpe]))
  buildChart(Chart, chartSharpeCompare, 'sharpeCompare', 'bar', shLabels, [
    { label: '指数夏普', data: shLabels.map((k) => idxShMap.get(k) ?? null), backgroundColor: 'rgba(13,110,253,0.45)', borderColor: '#0d6efd', borderWidth: 1 },
    { label: '模型夏普', data: shLabels.map((k) => stShMap.get(k) ?? null), backgroundColor: 'rgba(25,135,84,0.45)', borderColor: '#198754', borderWidth: 1 },
  ], baseChartOptions({ yTitle: 'Sharpe Ratio', xOpts: { ticks: { autoSkip: false, maxRotation: 60, minRotation: 20 } } }))

  // 9. 超额指标（夏普 / 索提诺）
  buildChart(Chart, chartExcessMetrics, 'excessMetrics', 'bar', ['excess_sharpe', 'excess_sortino'], [
    { label: 'Value', data: [r.excess_sharpe ?? null, r.excess_sortino ?? null], backgroundColor: ['rgba(13,110,253,0.5)', 'rgba(25,135,84,0.5)'], borderColor: ['#0d6efd', '#198754'], borderWidth: 1 },
  ], baseChartOptions({ yTitle: 'Metric Value' }))

  // 10. 最大回测修复天数（含年度最大值）
  const rdRows = repairDaysValues(r)
  if (rdRows.length) {
    buildChart(Chart, chartRepairDays, 'repairDays', 'bar', rdRows.map(([key]) => key), [
      { label: 'Repair Days', data: rdRows.map(([, value]) => Number(value)), backgroundColor: ['rgba(13,110,253,0.45)', 'rgba(25,135,84,0.45)', 'rgba(253,126,20,0.45)', 'rgba(13,110,253,0.45)', 'rgba(25,135,84,0.45)'].slice(0, rdRows.length), borderColor: ['#0d6efd', '#198754', '#fd7e14', '#0d6efd', '#198754'].slice(0, rdRows.length), borderWidth: 1 },
    ], baseChartOptions({ yTitle: 'Days' }))
  }

  // 11. 盈利月百分比（指数 vs 模型）
  const idxPm = new Map()
  const stPm = new Map()
  if (Array.isArray(r.index_profit_monthly)) r.index_profit_monthly.forEach((x) => { if (x) idxPm.set(String(x.year), x.profit_monthly_percentage) })
  if (Array.isArray(r.start_profit_monthly)) r.start_profit_monthly.forEach((x) => { if (x) stPm.set(String(x.year), x.profit_monthly_percentage) })
  const pmLabels = Array.from(new Set([...idxPm.keys(), ...stPm.keys()])).sort()
  buildChart(Chart, chartProfitMonthly, 'profitMonthly', 'line', pmLabels, [
    { label: '指数盈利月占比(%)', data: pmLabels.map((y) => (idxPm.get(y) ?? null) === null ? null : idxPm.get(y) * 100), borderColor: '#0d6efd', backgroundColor: 'rgba(13,110,253,0.08)', tension: 0.1, fill: true },
    { label: '模型盈利月占比(%)', data: pmLabels.map((y) => (stPm.get(y) ?? null) === null ? null : stPm.get(y) * 100), borderColor: '#198754', backgroundColor: 'rgba(25,135,84,0.08)', tension: 0.1, fill: true },
  ], baseChartOptions({ yTitle: 'Percentage (%)', yOpts: { beginAtZero: true, max: 100 } }))
}

// ── 生命周期 ─────────────────────────────────────────────────
onMounted(() => {
  updateSpreadsheetMeta()
  restoreRuntimeParams()
})

onBeforeUnmount(() => {
  clearTimeout(urlDebounceTimer)
  destroyAllCharts()
})
</script>

<style scoped>
.performance-analyzer-v2-input-head {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}

.performance-analyzer-v2-source-tabs {
  flex: 1;
  min-width: 0;
}

.performance-analyzer-v2-analyze-btn {
  margin-bottom: 16px;
}

.performance-analyzer-v2-meta {
  min-height: 1.2em;
  word-break: break-all;
}

.performance-analyzer-v2-mono :deep(.el-textarea__inner) {
  font-family: 'Fira Code', monospace;
}

.performance-analyzer-v2-info-box {
  height: 100%;
  padding: 14px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: var(--app-surface);
}

.performance-analyzer-v2-upload-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 176px;
  padding: 24px;
  border: 1px dashed var(--app-border);
  border-radius: 12px;
  text-align: center;
}

.performance-analyzer-v2-file-input {
  display: none;
}

.performance-analyzer-v2-info-title {
  margin-bottom: 8px;
  font-weight: 600;
}

.performance-analyzer-v2-info-subtitle {
  margin-bottom: 4px;
  font-size: var(--app-font-xs);
  font-weight: 600;
  color: var(--app-text-soft);
}

.performance-analyzer-v2-paste-status {
  margin-bottom: 12px;
}

.performance-analyzer-v2-excel-status {
  margin-top: 8px;
}

.performance-analyzer-v2-rule-row {
  display: flex;
  gap: 12px;
  margin-bottom: 6px;
  font-size: var(--app-font-xs);
}

.performance-analyzer-v2-rule-row span:first-child {
  flex: 0 0 64px;
  color: var(--app-text-muted);
}

.performance-analyzer-v2-rule-row span:last-child {
  flex: 1;
  color: var(--app-text-soft);
}

.performance-analyzer-v2-config-item {
  margin-bottom: 12px;
}

.performance-analyzer-v2-config-label {
  margin-bottom: 4px;
  font-size: var(--app-font-xs);
  font-weight: 600;
  color: var(--app-text-soft);
}

.performance-analyzer-v2-summary-grid {
  margin-bottom: 16px;
}

.performance-analyzer-v2-summary-grid__col,
.performance-analyzer-v2-chart-col,
.performance-analyzer-v2-block-col {
  margin-bottom: 12px;
}

.performance-analyzer-v2-summary-card {
  text-align: center;
}

.performance-analyzer-v2-summary-card--primary {
  border-color: var(--el-color-primary);
}

.performance-analyzer-v2-summary-card--success {
  border-color: var(--el-color-success);
}

.performance-analyzer-v2-summary-card--warning {
  border-color: var(--el-color-warning);
}

.performance-analyzer-v2-summary-card--danger {
  border-color: var(--el-color-danger);
}

.performance-analyzer-v2-summary-card--neutral {
  border-color: var(--el-color-info);
}

.performance-analyzer-v2-summary-card__label {
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
  margin-bottom: 4px;
}

.performance-analyzer-v2-summary-card__value {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 4px;
}

.performance-analyzer-v2-summary-card__key {
  color: var(--app-text-muted);
  font-size: 11px;
  font-family: 'Fira Code', monospace;
}

.performance-analyzer-v2-detail-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.performance-analyzer-v2-detail-actions {
  display: flex;
  gap: 8px;
}

.performance-analyzer-v2-block-title,
.performance-analyzer-v2-chart-title {
  margin-bottom: 8px;
  font-size: var(--app-font-sm);
  font-weight: 700;
}

.performance-analyzer-v2-chart-title {
  margin-bottom: 16px;
  font-size: var(--app-font-md);
}

.performance-analyzer-v2-chart-box--320 {
  height: 320px;
}

.performance-analyzer-v2-chart-box--340 {
  height: 340px;
}

.performance-analyzer-v2-raw-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.performance-analyzer-v2-raw-json {
  max-height: 520px;
}

.performance-analyzer-v2-stock-code {
  font-weight: 600;
  margin-right: 8px;
}

.performance-analyzer-v2-stock-label {
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}

.text-success {
  color: var(--el-color-success);
}

.text-danger {
  color: var(--el-color-danger);
}
</style>
