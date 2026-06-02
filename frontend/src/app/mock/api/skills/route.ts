export function GET() {
  return Response.json({
    skills: [
      {
        name: "skill-creator",
        description:
          "Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Claude's capabilities with specialized knowledge, workflows, or tool integrations.",
        license: "Complete terms in LICENSE.txt",
        category: "public",
        enabled: true,
      },
    ],
  });
}
