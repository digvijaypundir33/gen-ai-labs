

# DynamoDB on-demand capacity mode
<a name="on-demand-capacity-mode"></a>

Amazon DynamoDB on-demand offers a truly serverless database experience that automatically scales to accommodate the most demanding workloads without capacity planning. On-demand simplifies the setup process, eliminates capacity management and monitoring, and provides fast, automatic scaling. With pay-per-request pricing, you don’t have to worry about idle capacity because you only pay for the throughput you actually use. You are billed per read or write request, so your costs directly reflect your actual usage. 

When you choose on-demand mode, DynamoDB instantly accommodates your workloads as they ramp up or down to any previously reached traffic level. If a workload’s traffic level hits a new peak, DynamoDB automatically scales to accommodate the increased throughput requirements. On-demand mode is the default and recommended throughput option because it simplifies building modern, serverless applications that can start small and scale to millions of requests per second. Once your on-demand table is scaled out, you can instantly achieve the same throughput again in the future without throttling. If you are driving zero traffic to your table, then with on-demand, you are not charged for any throughput. For more information about on-demand mode's scaling properties, see [Initial throughput and scaling properties](#on-demand-capacity-mode-initial). 

Tables that use on-demand mode deliver the same single-digit millisecond latency, service-level agreement (SLA), and security that DynamoDB provisioned mode offers.

**Note**  
By default, DynamoDB protects you from unintended, runaway usage. To scale beyond the 40,000 table-level read and write throughput limits for all tables in your account, you can request an increase for this quota. Throughput requests that exceed the default table throughput quota are throttled. For more information, see [Throughput default quotas](ServiceQuotas.md#default-limits-throughput).

Optionally, you can also configure maximum read or write (or both) throughput per second for individual on-demand tables and global secondary indexes. By configuring throughput, you can keep table-level usage and costs bounded, protect against an inadvertent surge in consumed resources, and prevent excessive use for predictable cost management. Throughput requests that exceed the maximum table throughput are throttled. You can modify the table-specific maximum throughput at any time based on your application requirements. For more information, see [DynamoDB maximum throughput for on-demand tables](on-demand-capacity-mode-max-throughput.md).

To get started, create or update a table to use on-demand mode. For more information, see [Basic operations on DynamoDB tables](WorkingWithTables.Basics.md).

You can switch tables from provisioned capacity mode to on-demand mode up to four times in a 24-hour rolling window. You can switch tables from on-demand mode to provisioned capacity mode at any time. 

For more information about switching between read and write capacity modes, see [Considerations when switching capacity modes in DynamoDB](bp-switching-capacity-modes.md). For on-demand table quotas, see [Read/write throughput](ServiceQuotas.md#default-limits-throughput-capacity-modes).

**Topics**
+ [Read request units and write request units](#read-write-request-units)
+ [Initial throughput and scaling properties](#on-demand-capacity-mode-initial)
+ [DynamoDB maximum throughput for on-demand tables](on-demand-capacity-mode-max-throughput.md)

## Read request units and write request units
<a name="read-write-request-units"></a>

DynamoDB charges you for the reads and writes that your application performs on your tables in terms of *read request units* and *write request units*.

One *read request unit* represents one strongly consistent read operation per second, or two eventually consistent read operations per second, for an item up to 4 KB in size. For more information about DynamoDB read consistency models, see [DynamoDB read consistency](HowItWorks.ReadConsistency.md).

One *write request unit* represents one write operation per second, for an item up to 1 KB in size.

For more information about how read and write units are consumed, see [DynamoDB read and write operations](read-write-operations.md).

## Initial throughput and scaling properties
<a name="on-demand-capacity-mode-initial"></a>

DynamoDB tables using on-demand capacity mode automatically adapt to your application’s traffic volume. New on-demand tables will be able to sustain up to 4,000 writes per second and 12,000 reads per second. On-demand capacity mode instantly accommodates up to double the previous peak traffic on a table. For example, say that your application’s traffic pattern varies between 25,000 and 50,000 strongly consistent reads per second. 50,000 reads per second is the previous traffic peak. On-demand capacity mode instantly accommodates sustained traffic of up to 100,000 reads per second. If your application sustains traffic of 100,000 reads per second, that peak becomes your new previous peak. This previous peak enables subsequent traffic to reach up to 200,000 reads per second.

If your workload generates more than double your previous peak on a table, DynamoDB automatically allocates more capacity as your traffic volume increases. This capacity allocation helps ensure that your workload doesn't experience throttling. However, throttling can occur if you exceed double your previous peak within 30 minutes. For example, say that your application’s traffic pattern varies between 25,000 and 50,000 strongly consistent reads per second. 50,000 reads per second is the previously reached traffic peak. We recommend that you either pre-warm your table or space your traffic growth over at least 30 minutes before driving more than 100,000 reads per second. For more information about pre-warming, see [Understanding DynamoDB warm throughput](warm-throughput.md).

DynamoDB doesn’t place the 30 minute throttling restriction if your workload’s peak traffic remains within double your previous peak. If your peak traffic exceeds double the peak, make sure that this growth occurs 30 minutes after you last reached the peak.