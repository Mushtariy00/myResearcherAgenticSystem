/**
 * The ECharts runtime MetricsChart needs, tree-shaken from echarts/core (line series, grid,
 * legend, tooltip, canvas renderer). Imported on demand in the browser only.
 */
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

export { init };
