import React, { useState } from "react";
import { get } from "aws-amplify/api";
import { Button, Flex, Heading, TextField } from "@aws-amplify/ui-react";

export default function TicketLookup() {
  const [ticketId, setTicketId] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [ticket, setTicket] = useState(null);
  const [error, setError] = useState(null);

  const handleLookup = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setTicket(null);
    setError(null);

    try {
      const { body } = await get({
        apiName: "supportApi",
        path: `/tickets/${ticketId}`,
      }).response;
      setTicket(await body.json());
    } catch (err) {
      setError(err.message || "Ticket not found");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Flex direction="column" gap="1rem">
      <Heading level={3}>Look Up a Ticket</Heading>
      <form onSubmit={handleLookup}>
        <Flex direction="row" gap="0.5rem" alignItems="flex-end">
          <TextField
            label="Ticket ID"
            value={ticketId}
            onChange={(e) => setTicketId(e.target.value)}
            required
            width="100%"
          />
          <Button type="submit" isLoading={isLoading}>
            Look Up
          </Button>
        </Flex>
      </form>

      {ticket && (
        <Flex direction="column" gap="0.25rem" backgroundColor="rgba(0, 120, 200, 0.08)" padding="1rem" borderRadius="4px">
          <p><b>Subject:</b> {ticket.subject}</p>
          <p><b>Status:</b> {ticket.status}</p>
          <p><b>Category:</b> {ticket.category} <b>Priority:</b> {ticket.priority} <b>Urgency:</b> {ticket.urgency}</p>
          {ticket.ai_response && <p style={{ whiteSpace: "pre-wrap" }}><b>Response:</b> {ticket.ai_response}</p>}
        </Flex>
      )}
      {error && (
        <Flex backgroundColor="rgba(200, 0, 0, 0.1)" padding="1rem" borderRadius="4px">
          <p>{error}</p>
        </Flex>
      )}
    </Flex>
  );
}
