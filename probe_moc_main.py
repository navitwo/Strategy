import json
from AlgorithmImports import *


class Probe(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 6, 10)
        self.set_end_date(2024, 6, 11)
        self.set_time_zone(TimeZones.NEW_YORK)
        f = self.add_futures(Futures.Indices.NASDAQ_100_E_MINI,
                             Resolution.MINUTE)
        self.fut = f
        self.done = False

    def on_data(self, data):
        if self.done or not self.is_market_open(self.time):
            return
        t = self.time
        if not (t.hour == 9 and t.minute >= 35):
            return
        sym = self.fut.mapped
        tk = self.market_order(sym, 1, tag="probe-mkt")
        self.debug(f"PROBE ticket={tk} orderId={getattr(tk,'order_id',None)}")
        self.done = True

    def on_order_event(self, o):
        if o.status == OrderStatus.FILLED:
            self.RuntimeStatistics["filled"] = "1"
            self.RuntimeStatistics["fill_px"] = str(o.fill_price)
            self.RuntimeStatistics["fill_qty"] = str(o.fill_quantity)
        elif o.status in (OrderStatus.CANCELED, OrderStatus.INVALID):
            self.RuntimeStatistics["canceled"] = "1"
