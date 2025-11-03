import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { reminders } from "@/lib/schema";

export async function POST() {
  const dueAt = new Date(Date.now() + 1000 * 60 * 60 * 24);

  const [reminder] = await db
    .insert(reminders)
    .values({
      text: "Проверить новые заметки и ссылки в OVC.",
      dueAt,
      channel: "telegram",
      status: "pending"
    })
    .returning({
      id: reminders.id,
      text: reminders.text,
      dueAt: reminders.dueAt,
      channel: reminders.channel
    });

  return NextResponse.json({
    reminder,
    message: "Демо-напоминание создано."
  });
}
