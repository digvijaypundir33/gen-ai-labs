import React, { useState } from "react";
import { post, get } from "aws-amplify/api";
import { Button, Flex, Heading } from "@aws-amplify/ui-react";

const SUPPORTED_EXTENSIONS = ["docx", "pdf", "png", "jpg", "jpeg"];

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function FeedbackUpload({ job, setJob }) {
  const [file, setFile] = useState(null);
  const { status, result, isSubmitting } = job;

  const patchJob = (patch) => setJob((prev) => ({ ...prev, ...patch }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;

    const extension = file.name.split(".").pop().toLowerCase();
    if (!SUPPORTED_EXTENSIONS.includes(extension)) {
      patchJob({ status: `Unsupported file type. Use one of: ${SUPPORTED_EXTENSIONS.join(", ")}` });
      return;
    }

    patchJob({ isSubmitting: true, status: "Uploading...", result: null, jobId: null });

    try {
      const fileBase64 = await fileToBase64(file);
      const { body } = await post({
        apiName: "supportApi",
        path: "/feedback",
        options: { body: { fileBase64, fileExtension: extension } },
      }).response;
      const { jobId } = await body.json();
      patchJob({ jobId, status: `Processing job ${jobId}...` });

      const deadline = Date.now() + 30000;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 3000));
        const { body: pollBody } = await get({
          apiName: "supportApi",
          path: `/feedback/${jobId}`,
        }).response;
        const pollResult = await pollBody.json();
        if (pollResult.status === "Success") {
          patchJob({ result: pollResult, status: "Done" });
          break;
        }
      }
    } catch (error) {
      patchJob({ status: `Error: ${error.message}` });
    } finally {
      patchJob({ isSubmitting: false });
    }
  };

  return (
    <Flex direction="column" gap="1rem">
      <Heading level={3}>Upload Customer Feedback</Heading>
      <form onSubmit={handleSubmit}>
        <Flex direction="column" gap="1rem">
          <input
            type="file"
            accept=".docx,.pdf,.png,.jpg,.jpeg"
            onChange={(e) => setFile(e.target.files[0])}
          />
          <Button type="submit" variation="primary" isLoading={isSubmitting} isDisabled={!file}>
            Process Feedback
          </Button>
        </Flex>
      </form>

      {status && <p>{status}</p>}
      {result && (
        <Flex direction="column" gap="0.5rem" backgroundColor="rgba(0, 200, 0, 0.1)" padding="1rem" borderRadius="4px">
          <p><b>Summary:</b> {result.summary}</p>
          <p><b>Description:</b> {result.description}</p>
        </Flex>
      )}
    </Flex>
  );
}
