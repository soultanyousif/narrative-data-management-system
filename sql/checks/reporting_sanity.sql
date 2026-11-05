SELECT SUM(net_revenue_jpy) AS revenue_from_orders FROM reporting.orders;
SELECT ROUND(SUM(net_revenue_jpy)) AS revenue_from_lines FROM reporting.order_lines;
SELECT COUNT(*) AS counted_orders FROM reporting.orders WHERE is_counted;
SELECT COUNT(*) AS customers_with_orders FROM reporting.customer_summary WHERE counted_orders > 0;
SELECT COUNT(*) AS products FROM reporting.product_performance;
SELECT COUNT(*) FILTER (WHERE is_low_stock) AS low_stock,
       COUNT(*) FILTER (WHERE is_slow_mover) AS slow_movers
FROM reporting.product_performance;
SELECT customer_type, COUNT(*) FROM reporting.orders WHERE is_counted GROUP BY 1 ORDER BY 1;