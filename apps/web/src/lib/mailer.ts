import { createTransport, type Transporter } from "nodemailer";

let transporter: Transporter | null | undefined;

function getTransporter(): Transporter | null {
  if (transporter === undefined) {
    const url = process.env.SMTP_URL;
    transporter = url ? createTransport(url) : null;
  }
  return transporter;
}

export type MailMessage = { to: string; subject: string; text: string };

/**
 * Sends a plain-text email through `SMTP_URL` (Mailpit in development).
 * Returns false when SMTP is not configured or the server refuses the message; callers then
 * show the link to the admin instead, so invites keep working without SMTP.
 */
export async function sendMail(message: MailMessage): Promise<boolean> {
  const smtp = getTransporter();
  if (!smtp) {
    return false;
  }
  try {
    await smtp.sendMail({ from: process.env.MAIL_FROM ?? "no-reply@localhost", ...message });
    return true;
  } catch (error) {
    console.error("[mail] could not send email:", error instanceof Error ? error.message : error);
    return false;
  }
}
