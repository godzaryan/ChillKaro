import "./globals.css";

export const metadata = {
  title: "Chill karo — AI Exam Solver",
  description: "3-AI ensemble exam automation powered by Gemini, Groq & Cerebras",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
