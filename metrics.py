from opencensus.ext.azure import metrics_exporter
from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.stats import stats as stats_module
from opencensus.stats import view as view_module
from opencensus.tags import tag_map as tag_map_module
from users_data import azure_insights

stats = stats_module.stats
view_manager = stats.view_manager
stats_recorder = stats.stats_recorder

class Metrics:
    def __init__(self, export_metrics=False):
        self.nb_check_requests = measure_module.MeasureInt(
            "nb_check_requests",
            "number of dates check requests for all weeks",
            "nb"
        )
        self.nb_check_requests_view = view_module.View(
            "nb_check_requests view",
            "number of dates check requests for all weeks",
            [],
            self.nb_check_requests,
            aggregation_module.CountAggregation()
        )
        view_manager.register_view(self.nb_check_requests_view)
        self.mmap = stats_recorder.new_measurement_map()
        self.tmap = tag_map_module.TagMap()
        if export_metrics:
            exporter = metrics_exporter.new_metrics_exporter(
                connection_string=azure_insights.connection_string)
            view_manager.register_exporter(exporter)

    def check_request_sent(self):
        self.mmap.measure_int_put(self.nb_check_requests, 1)
        self.mmap.record(self.tmap)

metrics = Metrics()
