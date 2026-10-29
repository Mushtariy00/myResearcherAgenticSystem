import { describe, expect, it } from "vitest";
import { setPasswordEmail } from "./auth-emails";

describe("setPasswordEmail", () => {
  const data = {
    name: "Ji-woo",
    url: "http://localhost:8080/api/auth/reset-password/abc?callbackURL=%2Freset-password",
    hours: 48,
  };

  it("writes an invite in English and Korean with the link and its lifetime", () => {
    const { subject, text } = setPasswordEmail("invite", data);
    expect(subject).toContain("invited");
    expect(subject).toContain("초대");
    expect(text.split(data.url)).toHaveLength(3); // once per language
    expect(text).toContain("48 hours");
    expect(text).toContain("48시간");
    expect(text).toContain("Ji-woo님");
  });

  it("uses reset wording for a new password link", () => {
    const { subject } = setPasswordEmail("reset", data);
    expect(subject).toContain("new password");
    expect(subject).not.toContain("invited");
  });
});
