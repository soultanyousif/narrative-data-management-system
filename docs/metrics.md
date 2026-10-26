# Metric definitions (draft v1, to confirm with BoRu)

## General rules
- All money is reported in JPY. Each order stores its original currency, the exchange rate at order time, and the JPY amount.
- Only orders with status paid or fulfilled are counted. Cancelled and refunded orders are excluded.
- Prices are treated as tax-inclusive. Shipping is excluded from revenue.
- Dates are stored in UTC and shown in Japan time (JST).
- Offline sales may have no customer (walk-in buyers). They count in revenue and orders, but not in customer metrics.

## Metrics
- Revenue: sum of (unit price x quantity) for counted orders, in JPY.
- Orders: number of counted orders.
- Customers: number of distinct customers with at least one counted order in the period.
- Average order value (AOV): revenue divided by orders.
- New customer: first ever counted order falls in the period.
- Returning customer: had a counted order before the period.
- Repeat rate: returning customers divided by all customers in the period.
- Online share and offline share: revenue by channel divided by total revenue.
- Stock on hand: quantity in the latest inventory snapshot.
- Days of cover: stock on hand divided by average daily units sold over the last 30 days.
- Low stock: days of cover below 14, or stock on hand of 3 or fewer.
- Slow mover: product with no sales in the last 60 days and stock on hand above 0.

## Open questions for BoRu
1. Is revenue tax-inclusive or tax-exclusive?
2. Should shipping and refunds be included?
3. How are offline sales recorded today?