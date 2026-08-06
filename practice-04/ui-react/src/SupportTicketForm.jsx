import React, { useState } from "react";
import { post } from "aws-amplify/api";
import { Button, Flex, Heading, TextAreaField, TextField, SelectField } from "@aws-amplify/ui-react";

export default function SupportTicketForm() {
  const [formState, setFormState] = useState({
    subject: "",
    category: "technical",
    description: "",
    priority: "medium",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [response, setResponse] = useState(null);

  const handleChange = (e) => {
    setFormState({ ...formState, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setResponse(null);

    try {
      const { body } = await post({
        apiName: "supportApi",
        path: "/tickets",
        options: { body: formState },
      }).response;
      const result = await body.json();
      setResponse(result);
    } catch (error) {
      setResponse({ error: error.message || "Failed to submit ticket. Please try again." });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Flex direction="column" gap="1rem">
      <Heading level={3}>Submit Support Ticket</Heading>

      <form onSubmit={handleSubmit}>
        <Flex direction="column" gap="1rem">
          <TextField label="Subject" name="subject" value={formState.subject} onChange={handleChange} required />

          <SelectField label="Category" name="category" value={formState.category} onChange={handleChange}>
            <option value="technical">Technical Issue</option>
            <option value="billing">Billing Question</option>
            <option value="feature">Feature Request</option>
            <option value="other">Other</option>
          </SelectField>

          <TextAreaField
            label="Description"
            name="description"
            value={formState.description}
            onChange={handleChange}
            rows={5}
            required
          />

          <SelectField label="Priority" name="priority" value={formState.priority} onChange={handleChange}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </SelectField>

          <Button type="submit" variation="primary" isLoading={isSubmitting}>
            Submit Ticket
          </Button>
        </Flex>
      </form>

      {response && !response.error && (
        <Flex direction="column" gap="0.5rem" backgroundColor="rgba(0, 200, 0, 0.1)" padding="1rem" borderRadius="4px">
          <Heading level={5}>Ticket Processed</Heading>
          <p>Ticket ID: {response.ticketId}</p>
          <p>Status: {response.status}</p>
          <p>Category / Urgency: {response.classification?.category} / {response.classification?.urgency}</p>
          <p>Model used: {response.modelUsed}</p>
          <p style={{ whiteSpace: "pre-wrap" }}>AI Response: {response.aiResponse}</p>
        </Flex>
      )}

      {response && response.error && (
        <Flex backgroundColor="rgba(200, 0, 0, 0.1)" padding="1rem" borderRadius="4px">
          <p>{response.error}</p>
        </Flex>
      )}
    </Flex>
  );
}
