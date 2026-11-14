🎫 Built an AI support ticket system on AWS Bedrock. One bug in it taught me more about
cross-region inference than any doc I'd read.

Here's what actually happens when a ticket comes in:

1️⃣ You submit a ticket — subject, description, priority.
2️⃣ An AWS Strands Agent reads it and classifies category and urgency on its own
   (technical vs. billing vs. feature, low vs. critical). Nobody tells it what kind of
   ticket it is — it decides.
3️⃣ That classification feeds a Bedrock Knowledge Base lookup, which pulls whatever's
   actually relevant out of the indexed documentation, instead of the model just
   answering from memory.
4️⃣ Both feed a Bedrock Prompt Flow, which drafts the actual reply — and branches to a
   different model entirely depending on priority, so a "critical" ticket gets routed to
   a more capable model than a routine one.
5️⃣ A mock CRM step records the outcome.

⛓️ All five steps are chained by a Step Functions Express workflow, so it's one system
watching the ticket move through triage → research → drafting → resolution, not five
disconnected scripts.

🛠️ On top of the ticket flow itself: a live WebSocket mode streams a support-agent
response token by token instead of making you wait for the whole answer; a separate
Bedrock Data Automation pipeline takes an uploaded customer feedback document (a PDF, a
Word doc, a scanned image) and extracts a real generated summary out of it; and a React
+ Amplify frontend ties all of it together so you can actually click through the whole
thing in a browser instead of curling an API.

🐛 The one bug that taught me the most: Bedrock Data Automation has a "cross-region"
profile (`us.data-automation-v1`). I granted IAM access scoped to us-east-1, where
everything else in the project lives. Invocation failed with AccessDeniedException —
naming us-east-2. A region I never typed anywhere. Turns out that profile silently
routes the actual job to whichever US region has capacity, and your IAM policy has to
account for that or the error just looks broken. Same class of gotcha as Bedrock's
cross-region model inference profiles, just not documented as clearly.

📚 This is practice #4 in a series I'm building for real on my own AWS account as AWS
exam prep — every practice gets torn down to real bugs, real IAM errors, real cost
numbers, not just "here's a diagram." Full build log and write-up (all 16 stages, every
bug, every AWS resource and its teardown command) linked below. 👇

🔗 https://github.com/digvijaypundir33/gen-ai-labs

#awsexamprep #genai #aws #bedrock
