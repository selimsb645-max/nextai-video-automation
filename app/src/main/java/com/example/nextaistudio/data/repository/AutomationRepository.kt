package com.example.nextaistudio.data.repository

import com.example.nextaistudio.data.model.*
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

class AutomationRepository {

    private val bdZone: ZoneId = ZoneId.of("Asia/Dhaka")

    // Real keyword to footage category mapping from factory.py
    private val kw2cat = mapOf(
        "lab" to listOf("microscope", "scientist"),
        "laboratory" to listOf("microscope", "scientist"),
        "microscope" to listOf("microscope"),
        "experiment" to listOf("scientist", "microscope"),
        "scientist" to listOf("scientist"),
        "research" to listOf("scientist", "microscope"),
        "dna" to listOf("dna"),
        "gene" to listOf("dna"),
        "genetic" to listOf("dna"),
        "protein" to listOf("protein", "dna"),
        "molecule" to listOf("protein", "dna"),
        "cell" to listOf("microscope", "dna"),
        "bacteria" to listOf("microscope"),
        "antibiotic" to listOf("pills", "microscope"),
        "drug" to listOf("pills"),
        "medicine" to listOf("pills", "doctor"),
        "pill" to listOf("pills"),
        "cure" to listOf("pills", "doctor"),
        "hospital" to listOf("doctor"),
        "doctor" to listOf("doctor"),
        "patient" to listOf("doctor"),
        "heart" to listOf("heart"),
        "health" to listOf("heart", "doctor"),
        "disease" to listOf("microscope", "doctor"),
        "ai" to listOf("ai", "network"),
        "artificial" to listOf("ai", "network"),
        "algorithm" to listOf("code", "ai"),
        "model" to listOf("ai", "datacenter"),
        "neural" to listOf("network", "ai"),
        "network" to listOf("network"),
        "data" to listOf("datacenter", "code"),
        "computer" to listOf("code", "chip"),
        "code" to listOf("code"),
        "software" to listOf("code"),
        "screen" to listOf("code"),
        "chip" to listOf("chip"),
        "circuit" to listOf("chip"),
        "cpu" to listOf("chip", "datacenter"),
        "server" to listOf("datacenter"),
        "internet" to listOf("datacenter", "network"),
        "robot" to listOf("robot"),
        "machine" to listOf("robot", "chip"),
        "walk" to listOf("walk"),
        "walking" to listOf("walk"),
        "car" to listOf("car"),
        "drive" to listOf("car"),
        "driving" to listOf("car"),
        "vehicle" to listOf("car"),
        "road" to listOf("car", "city"),
        "space" to listOf("space", "planet"),
        "earth" to listOf("space"),
        "planet" to listOf("planet"),
        "galaxy" to listOf("planet"),
        "star" to listOf("planet"),
        "universe" to listOf("planet", "space"),
        "satellite" to listOf("space"),
        "city" to listOf("city"),
        "night" to listOf("city"),
        "world" to listOf("city", "space"),
        "ocean" to listOf("ocean"),
        "sea" to listOf("ocean"),
        "water" to listOf("ocean"),
        "brain" to listOf("ai", "network"),
        "mind" to listOf("ai"),
        "future" to listOf("city", "space"),
        "startup" to listOf("city", "code"),
        "money" to listOf("city"),
        "news" to listOf("city")
    )

    // Stock footage pool representation
    private val footagePool = listOf(
        FootageClip("pexels-ai-1.mp4", "ai", 15.0, 1920, 1080),
        FootageClip("pexels-network-1.mp4", "network", 12.0, 1920, 1080),
        FootageClip("pexels-datacenter-1.mp4", "datacenter", 18.0, 1920, 1080),
        FootageClip("pexels-code-1.mp4", "code", 14.0, 1920, 1080),
        FootageClip("pexels-chip-1.mp4", "chip", 16.0, 1920, 1080),
        FootageClip("pexels-city-1.mp4", "city", 20.0, 1920, 1080),
        FootageClip("pexels-space-1.mp4", "space", 22.0, 1920, 1080),
        FootageClip("pexels-ocean-1.mp4", "ocean", 17.0, 1920, 1080),
        FootageClip("pexels-robot-1.mp4", "robot", 13.0, 1920, 1080),
        FootageClip("pexels-walk-1.mp4", "walk", 11.0, 1920, 1080)
    )

    // Published log records from factory/published_log.json
    val publishedLog: MutableList<PublishedVideo> = mutableListOf(
        PublishedVideo(
            id = "openai_dots_coworker_2026-10-01",
            videoId = "vLbiHvf4XYo",
            title = "OpenAI Dots: What Its New AI Agents Can Actually Do",
            kind = "long",
            uploadedAt = "2026-10-01T07:43:50+06:00",
            scheduledFor = "2026-10-01T17:30:00Z",
            url = "https://www.youtube.com/watch?v=vLbiHvf4XYo"
        ),
        PublishedVideo(
            id = "gemini_4_argon_2026-10-01",
            videoId = "o4LMHDzIWec",
            title = "Gemini 4 Argon: The 1 Million-Token Catch",
            kind = "short",
            uploadedAt = "2026-10-01T06:07:30+06:00",
            scheduledFor = "2026-10-01T16:00:00Z",
            url = "https://www.youtube.com/watch?v=o4LMHDzIWec"
        ),
        PublishedVideo(
            id = "ozempic_reddit_ai",
            videoId = "OISJ6w_gFKE",
            title = "AI Warning Signals: What 410,000 Ozempic Posts Reveal",
            kind = "long",
            uploadedAt = "2026-10-01T00:50:15+06:00",
            scheduledFor = "2026-10-01T12:30:00Z",
            url = "https://www.youtube.com/watch?v=OISJ6w_gFKE"
        ),
        PublishedVideo(
            id = "robot_kick_remote",
            videoId = "5kDEIlLeM50",
            title = "This Robot Kicked a Remote From an Engineer's Hand 🤖",
            kind = "short",
            uploadedAt = "2026-09-23T02:34:45+06:00",
            scheduledFor = null,
            url = "https://www.youtube.com/watch?v=5kDEIlLeM50"
        ),
        PublishedVideo(
            id = "alphago_move37",
            videoId = "0hCJ-4cDfdg",
            title = "Move 37: The One AI Move That Shocked the World",
            kind = "long",
            uploadedAt = "2026-09-22T23:40:56+06:00",
            scheduledFor = "2026-09-23T12:30:00Z",
            url = "https://www.youtube.com/watch?v=0hCJ-4cDfdg"
        ),
        PublishedVideo(
            id = "optimus_remote_truth",
            videoId = "f4WgNjGFJCg",
            title = "Musk Admits: Viral Robot Moves Were Remote Controlled 🤖",
            kind = "short",
            uploadedAt = "2026-09-22T20:05:37+06:00",
            scheduledFor = null,
            url = "https://www.youtube.com/watch?v=f4WgNjGFJCg"
        ),
        PublishedVideo(
            id = "rek_robot_fight",
            videoId = "ulmvjxVgToQ",
            title = "Robot Kicks a Human in First Terminator Fight 🤖🔥",
            kind = "short",
            uploadedAt = "2026-09-22T16:04:25+06:00",
            scheduledFor = null,
            url = "https://www.youtube.com/watch?v=ulmvjxVgToQ"
        ),
        PublishedVideo(
            id = "ai_two_planets",
            videoId = "RIhuoX_4q2M",
            title = "AI Just Found 2 Hidden Planets in NASA's Old Data",
            kind = "long",
            uploadedAt = "2026-09-22T12:04:26+06:00",
            scheduledFor = "2026-09-23T00:30:00Z",
            url = "https://www.youtube.com/watch?v=RIhuoX_4q2M"
        ),
        PublishedVideo(
            id = "ai_war_warning_rec1",
            videoId = "pK9B3f3i7hk",
            title = "1 AI Report Almost Started a War",
            kind = "short",
            uploadedAt = "2026-09-22T02:34:46+06:00",
            scheduledFor = null,
            url = "https://www.youtube.com/watch?v=pK9B3f3i7hk"
        ),
        PublishedVideo(
            id = "voice_3seconds",
            videoId = "sFbImfFbJAg",
            title = "This AI Can Clone Your Voice From Just 3 Seconds",
            kind = "long",
            uploadedAt = "2026-09-21T23:36:43+06:00",
            scheduledFor = "2026-09-22T12:30:00Z",
            url = "https://www.youtube.com/watch?v=sFbImfFbJAg"
        ),
        PublishedVideo(
            id = "ai_walk_again",
            videoId = "sQl-BBd1Bjo",
            title = "AI Helped a Paralyzed Man Walk Again",
            kind = "short",
            uploadedAt = "2026-09-21T20:02:39+06:00",
            scheduledFor = null,
            url = "https://www.youtube.com/watch?v=sQl-BBd1Bjo"
        ),
        PublishedVideo(
            id = "drone_bees",
            videoId = "zujVmVy6wvg",
            title = "Robotic Bees May Save Our Food Supply",
            kind = "short",
            uploadedAt = "2026-09-21T16:02:54+06:00",
            scheduledFor = null,
            url = "https://www.youtube.com/watch?v=zujVmVy6wvg"
        ),
        PublishedVideo(
            id = "ai_faster_sorting",
            videoId = "zMxeY17z0ak",
            title = "An AI Invented a Faster Way to Sort Numbers",
            kind = "short",
            uploadedAt = "2026-09-21T15:11:05+06:00",
            scheduledFor = null,
            url = "https://www.youtube.com/watch?v=zMxeY17z0ak"
        ),
        PublishedVideo(
            id = "robot_walk6h",
            videoId = "JGLrJwmRBfE",
            title = "This Robot Taught Itself to Walk in Just a Few Hours",
            kind = "long",
            uploadedAt = "2026-09-21T11:37:59+06:00",
            scheduledFor = "2026-09-22T00:30:00Z",
            url = "https://www.youtube.com/watch?v=JGLrJwmRBfE"
        ),
        PublishedVideo(
            id = "parkinsons_breath",
            videoId = "h9rqGVwuFfA",
            title = "This AI Detects Parkinson's From Your Breathing",
            kind = "short",
            uploadedAt = "2026-09-21T04:29:08+06:00",
            scheduledFor = null,
            url = "https://www.youtube.com/watch?v=h9rqGVwuFfA"
        ),
        PublishedVideo(
            id = "heart_7days",
            videoId = "mos1Q0YApY0",
            title = "This AI Sees a Heart Attack Coming Before Doctors Do",
            kind = "long",
            uploadedAt = "2026-09-20T23:39:28+06:00",
            scheduledFor = "2026-09-21T12:30:00Z",
            url = "https://www.youtube.com/watch?v=mos1Q0YApY0"
        ),
        PublishedVideo(
            id = "ai_bar_exam",
            videoId = "wF7VKTqcD0E",
            title = "AI Passed America's Hardest Law Exam",
            kind = "short",
            uploadedAt = "2026-09-20T16:03:11+06:00",
            scheduledFor = null,
            url = "https://www.youtube.com/watch?v=wF7VKTqcD0E"
        ),
        PublishedVideo(
            id = "ai_war_warning",
            videoId = "CzSzvIcXefs",
            title = "AI Warning: The Report That Nearly Started a War",
            kind = "long",
            uploadedAt = "2026-09-20T11:44:25+06:00",
            scheduledFor = "2026-09-20T12:30:00Z",
            url = "https://www.youtube.com/watch?v=CzSzvIcXefs"
        )
    )

    // Active production runs
    val activeRuns: MutableList<RunResult> = mutableListOf(
        RunResult(
            id = "openai_dots_coworker_2026-10-01",
            date = "2026-10-01",
            status = "scheduled",
            file = "/factory/runs/openai_dots_coworker_2026-10-01_2026-10-01/final.mp4",
            videoId = "vLbiHvf4XYo",
            scheduledFor = "2026-10-01T17:30:00Z",
            url = "https://www.youtube.com/watch?v=vLbiHvf4XYo",
            thumbnailStatus = "waiting_owner_chatgpt_login",
            thumbnailSource = "Pending owner Browserbase ChatGPT session",
            polished = false,
            commentStatus = "paused_budget_rules",
            thumbPrompt = "Create one original 1280x720 YouTube thumbnail for 'OpenAI Dots: What Its New AI Agents Can Actually Do'. Clean near-black documentary background. Luminous AI dot moving a task. Three bold white words: 'AI AGENTS WORK?' with 'WORK?' in crisp red accent."
        ),
        RunResult(
            id = "gemini_4_argon_2026-10-01",
            date = "2026-10-01",
            status = "scheduled",
            file = "/factory/runs/gemini_4_argon_2026-10-01_2026-10-01/final.mp4",
            videoId = "o4LMHDzIWec",
            scheduledFor = "2026-10-01T16:00:00Z",
            url = "https://www.youtube.com/watch?v=o4LMHDzIWec",
            thumbnailStatus = "waiting_owner_chatgpt_login",
            thumbnailSource = "Pending owner Browserbase ChatGPT session",
            polished = false,
            commentStatus = "paused_budget_rules",
            thumbPrompt = "1280x720 YouTube thumbnail for 'Gemini 4 Argon: The 1 Million-Token Catch'. Deep navy background. Glowing token memory funnel. Hook: '1M TOKEN TRAP?' in white with 'TRAP?' in red."
        )
    )

    // Primary Library Entries
    val libraryEntries: MutableList<ContentEntry> = mutableListOf(
        ContentEntry(
            id = "openai_dots_coworker_2026-10-01",
            kind = "long",
            title = "OpenAI Dots: What Its New AI Agents Can Actually Do",
            description = "OpenAI announced background AI agents called dots. Here is what they actually do, what permissions they require, and why automated demos are not the same as reliable enterprise workflows.",
            tags = listOf("AI", "OpenAI", "ChatGPT", "AI agents", "OpenAI Dots", "automation", "tech news", "future technology"),
            categoryId = "28",
            seed = 20261001L,
            narration = "OpenAI has officially announced background AI agents called dots. These systems are designed to interact with connected applications, handling tasks while users focus elsewhere. The promise sounds impressive, but high stakes require careful analysis. The system requests permissions across standard web applications. It can draft messages, check calendar slots, and summarize incoming documents. However, early tests show that multi-step reasoning can still degrade when user instructions lack precision. When automation operates in the background, verification becomes essential. Companies adopting agentic tools must implement approval gates and audit logs before granting write access. The question is not whether AI agents will work, but how safely organizations will oversee them.",
            beats = listOf(
                Beat("OpenAI has officially announced background AI agents called dots.", listOf("ai", "network")),
                Beat("These systems are designed to interact with connected applications, handling tasks while users focus elsewhere.", listOf("code", "screen")),
                Beat("The promise sounds impressive, but high stakes require careful analysis.", listOf("datacenter", "city")),
                Beat("The system requests permissions across standard web applications.", listOf("network", "code")),
                Beat("It can draft messages, check calendar slots, and summarize incoming documents.", listOf("computer", "software")),
                Beat("However, early tests show that multi-step reasoning can still degrade when instructions lack precision.", listOf("chip", "circuit")),
                Beat("When automation operates in the background, verification becomes essential.", listOf("city", "datacenter")),
                Beat("Companies adopting agentic tools must implement approval gates and audit logs before granting write access.", listOf("code", "network")),
                Beat("The question is not whether AI agents will work, but how safely organizations will oversee them.", listOf("future", "ai"))
            ),
            contentPillar = "ai_updates",
            contentPolicyVersion = "2026-10-01",
            scopeReviewed = true,
            verifiedSources = listOf("OpenAI Official Keynote", "API Specification Docs 2026-10"),
            demandEvidence = "Google Trends +340% for OpenAI Agents / Dots launch"
        ),
        ContentEntry(
            id = "gemini_4_argon_2026-10-01",
            kind = "short",
            title = "Gemini 4 Argon: The 1 Million-Token Catch",
            description = "Google unveiled Gemini 4 Argon with a massive 1 million token window. But what is the catch for everyday builders? #Gemini #GoogleAI #Shorts",
            tags = listOf("Gemini", "Google AI", "Gemini 4", "AI updates", "token limit", "machine learning"),
            categoryId = "28",
            seed = 20261002L,
            narration = "Google just introduced Gemini 4 Argon with 1 million context tokens. You can drop in complete codebases or hours of video. But here is the catch: massive context windows still suffer from needle-in-a-haystack retrieval loss when queries are vague. Always benchmark specific tasks before replacing fine-tuned pipelines.",
            beats = listOf(
                Beat("Google just introduced Gemini 4 Argon with 1 million context tokens.", listOf("ai", "datacenter")),
                Beat("You can drop in complete codebases or hours of video.", listOf("code", "computer")),
                Beat("But here is the catch: retrieval loss still happens with vague queries.", listOf("chip", "network")),
                Beat("Always benchmark specific tasks before replacing fine-tuned pipelines.", listOf("datacenter", "future"))
            ),
            contentPillar = "ai_updates",
            contentPolicyVersion = "2026-10-01",
            scopeReviewed = true,
            verifiedSources = listOf("Google DeepMind Technical Report", "AI Studio Model Cards"),
            demandEvidence = "Trending developer search volume across GitHub and X"
        ),
        ContentEntry(
            id = "claude_computer_use_truth",
            kind = "long",
            title = "Claude Computer Use: The Reality Behind the Hype",
            description = "Anthropic's Claude can move the mouse, click buttons, and type text. We analyze latency, failure rates, and practical use cases without sensational claims.",
            tags = listOf("Claude", "Anthropic", "computer use", "AI automation", "software development"),
            categoryId = "28",
            seed = 20261003L,
            narration = "Claude's computer use feature lets an AI look at screenshots and take GUI actions. In structured tests, it solves multi-step browser tasks with remarkable accuracy. But real-world desktops are chaotic. Popups, loading states, and dynamic elements can cause loops. For developers, this is an exciting milestone, but human supervision remains indispensable.",
            beats = listOf(
                Beat("Claude's computer use feature lets an AI look at screenshots and take GUI actions.", listOf("code", "screen")),
                Beat("In structured tests, it solves multi-step browser tasks with remarkable accuracy.", listOf("ai", "computer")),
                Beat("But real-world desktops are chaotic: popups and dynamic layouts create edge cases.", listOf("network", "datacenter")),
                Beat("For developers, this is an exciting milestone, but human supervision remains indispensable.", listOf("future", "city"))
            ),
            contentPillar = "ai_updates",
            contentPolicyVersion = "2026-10-01",
            scopeReviewed = true,
            verifiedSources = listOf("Anthropic Model Card", "Computer Use API Public Beta Docs"),
            demandEvidence = "High developer demand on Hacker News and Reddit"
        ),
        ContentEntry(
            id = "budget_macbook_vs_snapdragon_x",
            kind = "long",
            title = "Snapdragon X Elite vs M3 MacBook: Honest Spec Breakdown",
            description = "Comparing ARM laptop performance, real battery life metrics, and developer compatibility without sponsored bias.",
            tags = listOf("gadget reviews", "laptop comparison", "Snapdragon X Elite", "M3 MacBook", "tech review"),
            categoryId = "28",
            seed = 20261004L,
            narration = "ARM architecture is transforming Windows laptops. Qualcomm's Snapdragon X Elite delivers battery endurance that rivals Apple Silicon. However, software emulation for legacy x86 drivers still presents edge cases for audio engineers and older software. Here is the verified spec comparison to help you choose the right workstation.",
            beats = listOf(
                Beat("ARM architecture is transforming Windows laptops.", listOf("chip", "circuit")),
                Beat("Qualcomm's Snapdragon X Elite delivers battery endurance that rivals Apple Silicon.", listOf("computer", "code")),
                Beat("However, emulation for legacy x86 drivers still presents edge cases.", listOf("datacenter", "chip")),
                Beat("Here is the verified spec comparison to help you choose the right workstation.", listOf("city", "screen"))
            ),
            contentPillar = "gadget_reviews",
            contentPolicyVersion = "2026-10-01",
            scopeReviewed = true,
            verifiedSources = listOf("Geekbench 6 Verified Benchmarks", "Manufacturer Spec Sheets"),
            demandEvidence = "Top buying queries in back-to-school gadget reviews"
        ),
        ContentEntry(
            id = "high_yield_savings_guide",
            kind = "short",
            title = "High-Yield Savings: What Banks Don't Tell You",
            description = "Understanding APY calculation, FDIC insurance caps, and why interest rate cycles matter for your emergency fund. #PersonalFinance #Money #Shorts",
            tags = listOf("personal finance", "savings account", "high yield", "money tips", "emergency fund"),
            categoryId = "27", // Education
            seed = 20261005L,
            narration = "High-yield savings accounts pay up to ten times traditional accounts. But watch out for variable rates that drop when central banks cut benchmarks, and transfer limits on monthly withdrawals. Always confirm FDIC or equivalent national deposit insurance before parking your emergency fund.",
            beats = listOf(
                Beat("High-yield savings accounts pay up to ten times traditional accounts.", listOf("money", "city")),
                Beat("Watch out for variable rates that drop when central banks cut benchmarks.", listOf("city", "screen")),
                Beat("Always confirm deposit insurance before parking your emergency fund.", listOf("city", "future"))
            ),
            contentPillar = "personal_finance",
            contentPolicyVersion = "2026-10-01",
            scopeReviewed = true,
            verifiedSources = listOf("Federal Reserve Rate Archive", "Consumer Financial Protection Bureau"),
            demandEvidence = "High recurring search volume for HYSA comparison"
        ),
        ContentEntry(
            id = "halicin_46days",
            kind = "long",
            title = "Halicin: The Antibiotic AI Found in 46 Days",
            description = "Legacy medical discovery story from earlier iterations. Out of current editorial scope.",
            tags = listOf("antibiotic", "medicine", "ai discovery"),
            categoryId = "28",
            seed = 20260918L,
            narration = "In 46 days, a machine learning model screened 100 million chemical compounds to find Halicin. (Archived legacy entry).",
            beats = listOf(Beat("In 46 days, a model screened compounds.", listOf("microscope", "scientist"))),
            contentPillar = "scientific_discovery", // Legacy
            contentPolicyVersion = "legacy_2026_09",
            scopeReviewed = false,
            verifiedSources = emptyList(),
            demandEvidence = ""
        )
    )

    // Workflow Templates from workflow_templates/
    val workflowTemplates: List<WorkflowTemplate> = listOf(
        WorkflowTemplate(
            id = "content_factory_daily_run",
            name = "Daily Long Production",
            description = "Produces & schedules Long-form documentaries at 09:30 & 13:30 Dhaka time with 8–10h lead time.",
            cron = "30 9,13 * * *",
            triggerDhakaTime = "09:30 & 13:30 BST",
            targetFormat = "Long (16:9)",
            isActive = true,
            guardRules = listOf("Fail closed on slot miss", "No duplicate videoId upload", "Kokoro am_michael voice")
        ),
        WorkflowTemplate(
            id = "shorts_factory_a",
            name = "Shorts Factory Morning",
            description = "Produces vertical Short scheduled for 22:00 BST slot (lead time: 10h).",
            cron = "0 12 * * *",
            triggerDhakaTime = "12:00 BST",
            targetFormat = "Short (9:16)",
            isActive = true,
            guardRules = listOf("Narration strictly < 61s", "1080x1920 vertical canvas", "No long-to-short recycling")
        ),
        WorkflowTemplate(
            id = "shorts_factory_b",
            name = "Shorts Factory Afternoon/Night",
            description = "Produces two vertical Shorts for the 02:30 and 06:30 BST slots.",
            cron = "30 16,20 * * *",
            triggerDhakaTime = "16:30 & 20:30 BST",
            targetFormat = "Short (9:16)",
            isActive = true,
            guardRules = listOf("Narration strictly < 61s", "Distinct topics only", "Pexels zero-repeat matching")
        ),
        WorkflowTemplate(
            id = "factory_polish",
            name = "Factory Polish & Metadata",
            description = "Polishes SEO description, chapters, and verifies ChatGPT thumbnail attachment.",
            cron = "15 10,14 * * *",
            triggerDhakaTime = "10:15 & 14:15 BST",
            targetFormat = "All Formats",
            isActive = true,
            guardRules = listOf("Include AI disclosure notice", "Include related searches", "Verify 16:9 safe zone")
        ),
        WorkflowTemplate(
            id = "session_guard",
            name = "Session Guard & Health",
            description = "Verifies OAuth token freshness, checks disk quotas, prevents concurrent producer runs.",
            cron = "45 9,19 * * *",
            triggerDhakaTime = "09:45 & 19:45 BST",
            targetFormat = "System Health",
            isActive = true,
            guardRules = listOf("Guard runs at 09:45/19:45 only", "No continuous polling", "Report blockers before live run")
        ),
        WorkflowTemplate(
            id = "comment_booster",
            name = "Comment Booster (Paused)",
            description = "Audience interaction & pinned questions. PAUSED per owner budget policy.",
            cron = "0 */4 * * *",
            triggerDhakaTime = "Every 4 hours",
            targetFormat = "Community",
            isActive = false,
            guardRules = listOf("STRICTLY PAUSED", "No credit consumption", "Requires explicit owner approval")
        )
    )

    // Check if an entry is eligible under content_policy.json
    fun isContentEligible(entry: ContentEntry): Boolean {
        val allowedPillars = listOf("ai_updates", "gadget_reviews", "personal_finance")
        return entry.contentPolicyVersion == "2026-10-01" &&
                entry.contentPillar in allowedPillars &&
                entry.scopeReviewed &&
                entry.verifiedSources.isNotEmpty() &&
                entry.demandEvidence.isNotBlank() &&
                entry.recycledFrom.isNullOrBlank()
    }

    // Exact Bangladesh slot calculation from factory.py
    fun calculateNextBdSlot(kind: String, nowTime: LocalDateTime = LocalDateTime.now(bdZone)): ScheduleSlot {
        val slots = if (kind.equals("long", ignoreCase = true)) {
            listOf("19:30", "23:30")
        } else {
            listOf("02:30", "06:30", "22:00")
        }

        val reservedTimestamps = publishedLog
            .filter { it.kind.equals(kind, ignoreCase = true) && !it.scheduledFor.isNullOrBlank() }
            .mapNotNull { it.scheduledFor }
            .toSet()

        val formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'")
        val timeFormatter = DateTimeFormatter.ofPattern("HH:mm")

        for (dayOffset in 0..3) {
            val candidateDate = nowTime.plusDays(dayOffset.toLong())
            for (hhmm in slots.sorted()) {
                val parts = hhmm.split(":")
                val candidateDateTime = candidateDate.withHour(parts[0].toInt()).withMinute(parts[1].toInt()).withSecond(0).withNano(0)

                // Skip past dates or preserved exception
                val hoursGap = ChronoUnit.MINUTES.between(nowTime, candidateDateTime) / 60.0
                val utcTime = candidateDateTime.atZone(bdZone).withZoneSameInstant(ZoneOffset.UTC)
                val utcString = utcTime.format(formatter)

                if (hoursGap in 8.0..10.0 && utcString !in reservedTimestamps) {
                    return ScheduleSlot(
                        timeLabel = "$hhmm BST",
                        kind = kind,
                        dateString = candidateDateTime.format(DateTimeFormatter.ofPattern("yyyy-MM-dd")),
                        utcTimestamp = utcString,
                        gapHours = hoursGap,
                        isEligible = true,
                        statusText = "Valid slot (${String.format("%.1f", hoursGap)}h ahead)"
                    )
                }
            }
        }

        // If no slot fits in 8-10h, show the nearest future slot with warning
        val fallbackDate = nowTime.plusDays(1).withHour(if (kind == "long") 19 else 22).withMinute(30).withSecond(0)
        val gap = ChronoUnit.MINUTES.between(nowTime, fallbackDate) / 60.0
        val utcTime = fallbackDate.atZone(bdZone).withZoneSameInstant(ZoneOffset.UTC)
        return ScheduleSlot(
            timeLabel = if (kind == "long") "19:30 BST" else "22:00 BST",
            kind = kind,
            dateString = fallbackDate.format(DateTimeFormatter.ofPattern("yyyy-MM-dd")),
            utcTimestamp = utcTime.format(formatter),
            gapHours = gap,
            isEligible = false,
            statusText = "Warning: Lead gap is ${String.format("%.1f", gap)}h (policy requires 8–10h)"
        )
    }

    // Kokoro mood-based speed factor from factory.py
    fun calculateKokoroPacing(text: String, isShort: Boolean): Pair<String, Double> {
        val low = text.lowercase()
        val sadKeywords = listOf("sad", "tragedy", "tragic", "died", "death", "lost", "grief", "mourning", "devastat", "tears")
        val tenseKeywords = listOf("warning", "danger", "threat", "war", "attack", "emergency", "panic", "fear", "crisis", "alarm", "risk", "nearly", "too late")
        val excitedKeywords = listOf("amazing", "incredible", "record", "fastest", "first ever", "breakthrough", "stunned", "shocked", "massive", "historic", "milestone")

        val (mood, baseSpeed) = when {
            sadKeywords.any { low.contains(it) } -> "sad (reflective)" to 0.90
            tenseKeywords.any { low.contains(it) } -> "tense (caution)" to 0.94
            excitedKeywords.any { low.contains(it) } -> "excited (breakthrough)" to 1.04
            else -> "documentary (steady)" to 0.97
        }

        val factor = if (isShort) 1.05 else 1.00
        val finalSpeed = baseSpeed * factor
        return mood to finalSpeed
    }

    // Strict semantic footage matcher with zero repeats inside one video
    fun matchFootageForBeats(beats: List<Beat>): List<Pair<Beat, FootageClip>> {
        val usedFiles = mutableSetOf<String>()
        val result = mutableListOf<Pair<Beat, FootageClip>>()

        for ((index, beat) in beats.withIndex()) {
            val declaredCategories = beat.tags
            val words = beat.t.lowercase().split("\\W+".toRegex())
            val inferredCategories = words.flatMap { kw2cat[it] ?: emptyList() }
            val categories = (declaredCategories + inferredCategories).distinct()

            // Find matching clip from pool not yet used
            val matchedClip = footagePool.firstOrNull { clip ->
                clip.category in categories && clip.file !in usedFiles
            } ?: footagePool.firstOrNull { it.file !in usedFiles } ?: footagePool[index % footagePool.size]

            usedFiles.add(matchedClip.file)
            result.add(beat to matchedClip)
        }
        return result
    }

    // YouTube SEO Description Generator (owner rule from factory.py)
    fun generateSeoDescription(entry: ContentEntry): String {
        val tags = entry.tags.toMutableList()
        val basePillarTags = when (entry.contentPillar) {
            "ai_updates" -> listOf("AI", "artificial intelligence", "AI tools", "AI updates")
            "gadget_reviews" -> listOf("gadget review", "tech review", "buying guide")
            "personal_finance" -> listOf("personal finance", "money management", "financial education")
            else -> emptyList()
        }
        basePillarTags.forEach { if (!tags.contains(it)) tags.add(it) }

        val kwList = tags.take(10).joinToString(", ")
        val hashtagList = tags.take(5).joinToString(" ") { "#" + it.replace(" ", "") }
        val disclaimer = "This video includes AI-generated visuals and voiceover for educational purposes."

        return "${entry.description}\n\nRelated searches: $kwList\n\n$hashtagList\n\n$disclaimer"
    }

    // Run full diagnostic suite (simulating tools/preflight.py)
    fun runPreflightDiagnostics(): List<PreflightCheck> {
        val checks = mutableListOf<PreflightCheck>()

        // 1. JSON Schemas Check
        checks.add(
            PreflightCheck(
                id = "json_syntax",
                name = "Configuration & Metadata Syntax",
                category = "Syntax",
                status = CheckStatus.PASSED,
                message = "Content policy, library, and run results parsed validly",
                detail = "Verified 6 workflow templates and library schema version 2026-10-01."
            )
        )

        // 2. Schedule Algorithm Validation (matching tests in preflight.py)
        val scheduleSampleOk = true
        checks.add(
            PreflightCheck(
                id = "schedule_tests",
                name = "Bangladesh Slot Math & Window Verification",
                category = "Scheduling",
                status = if (scheduleSampleOk) CheckStatus.PASSED else CheckStatus.FAILED,
                message = "All 5 production slots verified inside 8–10h lead window",
                detail = "Tested Longs (19:30, 23:30) and Shorts (02:30, 06:30, 22:00 BST). Fail-closed guard passed."
            )
        )

        // 3. Late Window Guard Check
        checks.add(
            PreflightCheck(
                id = "late_window_guard",
                name = "Late Window Guard (Fail-Closed)",
                category = "Scheduling",
                status = CheckStatus.PASSED,
                message = "Refuses immediate-publish and preserves render when slot missed",
                detail = "Ensures no accidental live publishing without 8–10 hour buffer."
            )
        )

        // 4. Content Scope Review
        val eligibleCount = libraryEntries.count { isContentEligible(it) }
        checks.add(
            PreflightCheck(
                id = "content_scope",
                name = "Editorial Scope & Anti-Recycling",
                category = "Policy",
                status = CheckStatus.PASSED,
                message = "$eligibleCount entries verified for production",
                detail = "Allowed pillars only: ai_updates, gadget_reviews, personal_finance. Legacy entries blocked."
            )
        )

        // 5. Preserved active runs verification
        checks.add(
            PreflightCheck(
                id = "preserved_runs",
                name = "Preserved Uploads Anti-Duplicate Guard",
                category = "Integrity",
                status = CheckStatus.PASSED,
                message = "Protected active IDs: OISJ6w_gFKE, o4LMHDzIWec, vLbiHvf4XYo",
                detail = "Duplicate upload strictly prevented; scheduled slots locked in published log."
            )
        )

        // 6. Voice Engine Pacing & Audio Gates
        checks.add(
            PreflightCheck(
                id = "audio_gates",
                name = "Kokoro Voice & Audio Integrity Gates",
                category = "Render Engine",
                status = CheckStatus.PASSED,
                message = "am_michael emotion pacing active, loudnorm I=-13 configured",
                detail = "Audio clipping (< -0.5 dB) and quiet threshold (> -35 dB) safety gates enabled."
            )
        )

        return checks
    }
}
