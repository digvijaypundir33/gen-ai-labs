import { useState } from "react";
import "@aws-amplify/ui-react/styles.css";
import { Flex, Heading, ToggleButtonGroup, ToggleButton } from "@aws-amplify/ui-react";
import "./amplifyConfig";
import SupportTicketForm from "./SupportTicketForm";
import TicketLookup from "./TicketLookup";
import LiveChat from "./LiveChat";
import FeedbackUpload from "./FeedbackUpload";

const MODES = {
  submit: SupportTicketForm,
  lookup: TicketLookup,
  chat: LiveChat,
  feedback: FeedbackUpload,
};

// Lifted up so an in-flight/completed feedback job survives switching tabs and back —
// FeedbackUpload itself unmounts on tab switch (its local state would otherwise reset).
const initialFeedbackJob = { jobId: null, status: null, result: null, isSubmitting: false };

function App() {
  const [mode, setMode] = useState("submit");
  const [feedbackJob, setFeedbackJob] = useState(initialFeedbackJob);
  const ActiveComponent = MODES[mode];

  return (
    <Flex direction="column" gap="1.5rem" maxWidth="700px" margin="2rem auto" padding="1rem">
      <Heading level={2}>Practice 04 — Support Ticket System</Heading>

      <ToggleButtonGroup value={mode} onChange={(value) => setMode(value)} isExclusive>
        <ToggleButton value="submit">Submit Ticket</ToggleButton>
        <ToggleButton value="lookup">Look Up Ticket</ToggleButton>
        <ToggleButton value="chat">Live Chat</ToggleButton>
        <ToggleButton value="feedback">Feedback Upload</ToggleButton>
      </ToggleButtonGroup>

      {mode === "feedback" ? (
        <FeedbackUpload job={feedbackJob} setJob={setFeedbackJob} />
      ) : (
        <ActiveComponent />
      )}
    </Flex>
  );
}

export default App;
