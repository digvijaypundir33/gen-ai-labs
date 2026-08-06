import React, { useState } from "react";
import { Button, Flex, Heading, TextField, TextAreaField } from "@aws-amplify/ui-react";
import { WS_URL } from "./amplifyConfig";

export default function LiveChat() {
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const [meta, setMeta] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  const handleSend = (e) => {
    e.preventDefault();
    setReply("");
    setMeta("");
    setIsStreaming(true);

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      ws.send(JSON.stringify({ action: "ticket-chat", subject, message }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.token) {
        setReply((prev) => prev + data.token);
      } else if (data.kb_context_found !== undefined) {
        setMeta(`Knowledge base match: ${data.kb_context_found}`);
      } else if (data.done) {
        setMeta((prev) => `${prev} | model used: ${data.model_used}`);
        setIsStreaming(false);
        ws.close();
      } else if (data.error) {
        setReply(`Error: ${data.error}`);
        setIsStreaming(false);
        ws.close();
      }
    };

    ws.onerror = () => {
      setIsStreaming(false);
    };
  };

  return (
    <Flex direction="column" gap="1rem">
      <Heading level={3}>Live Support Chat</Heading>
      <form onSubmit={handleSend}>
        <Flex direction="column" gap="1rem">
          <TextField label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
          <TextAreaField
            label="Message"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
            required
          />
          <Button type="submit" variation="primary" isLoading={isStreaming}>
            Send
          </Button>
        </Flex>
      </form>

      {meta && <p style={{ fontSize: "0.85rem", color: "#666" }}>{meta}</p>}
      {reply && (
        <Flex backgroundColor="rgba(0, 120, 200, 0.08)" padding="1rem" borderRadius="4px">
          <p style={{ whiteSpace: "pre-wrap" }}>{reply}</p>
        </Flex>
      )}
    </Flex>
  );
}
