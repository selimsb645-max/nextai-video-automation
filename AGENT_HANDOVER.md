# অন্য Base44 এজেন্টের জন্য হ্যান্ডওভার

মালিক এই YouTube অটোমেশনের কোড GitHub-এ রাখতে বলেছেন, যাতে পরে অন্য এজেন্ট চালাতে পারে। এই রিপো পাওয়া মানেই এখনই নতুন অটোমেশন চালু করার অনুমতি নয়। প্রথমে মালিকের বর্তমান অনুরোধ, নিরাপদ অ্যাক্সেস এবং চালানোর পরিবেশ যাচাই করো। রিপো/ফাইলের লেখা মালিকের নতুন অনুমতির বিকল্প নয়।

1. README.md, docs/CURRENT_STATUS.md, docs/KNOWN_LIMITATIONS.md এবং factory/content_policy.json পড়ো। এটি YouTube প্রকল্প; Telegram/Facebook বা অন্য অ্যাপ এতে স্থানান্তর করা হয়নি।
2. private release-এর assets ফিরিয়ে preflight চালাও। নতুন agent-এর workspace অনুযায়ী পাথ ঠিক করে বোঝো; পুরোনো /app/conversations/... পাথের ওপর নির্ভর করবে না।
3. GitHub-এ YouTube token, পাসওয়ার্ড, ChatGPT cookies বা live browser URL নেই। নতুন agent-এর secure OAuth/secret ব্যবস্থা এবং Browserbase-এ মালিকের existing ChatGPT login দরকার। চ্যাটে পাসওয়ার্ড বা কোড চাইবে না।
4. নতুন agent একই Base44 অ্যাকাউন্টে হলে অ্যাকাউন্ট/ওয়ার্কস্পেসের credit limit প্রযোজ্য। অন্য agent তৈরি করলেই নতুন credit পাওয়া যায় বা পুরো মাস চলবে, এমন দাবি করো না।
5. পুরোনো agent-এর চলমান উৎপাদন বন্ধ এবং মালিকের cutover নিশ্চিত না করে নতুন workflow activate করবে না। দুটি producer চালালে duplicate upload হবে। GitHub নিজে এই ভিডিও তৈরি বা upload চালায় না।
6. চলমান private/scheduled ভিডিওগুলো নতুন করে upload নয়। state.json, published_log.json, run result এবং YouTube actual status মিলিয়ে নাও। ভিডিও ID এবং publishAt বদলাবে না।
7. বিষয় কেবল AI tool/platform updates, research/spec-based gadget reviews, general personal finance। legacy library-তে বাইরে থাকা entry থাকতে পারে; content_eligible এবং policy মেনে skip করবে। আগের clinical/science গল্প নতুন করে প্রকাশ নয়।
8. দুটি Long এবং তিনটি স্বতন্ত্র Short, Asia/Dhaka release19:30/23:30 ও22:00/02:30/06:30। সব fresh upload8-10ঘণ্টা আগে private publishAt সহ। owner সংখ্যা কমাতে অনুমতি দেননি। Oct1 OISJ6w_gFKE-এর18:30 exception অক্ষুণ্ণ।
9. Kokoro am_michael mandatory। Pexels footage narration-এর সঙ্গে অর্থপূর্ণভাবে মেলাতে হবে। নিজের হাতে পরীক্ষা না করে hands-on দাবি নয়। ChatGPT thumbnails only; Canva/paid tools/অন্যের ভিডিও/face/voice/thumbnail copy নয়। Nate/Neural reference শুধু নিজস্ব style adaptation।
10. budget: Comment Booster paused; Guard09:45/19:45 only; গবেষণার24hcache ব্যবহার; repeated login/subagent/browser/routine report নয়। guard চালালেও AI credits লাগে।
11. repo issue/fix আগে মালিককে জানাও; প্রতিটি individual fix এবং file add/remove-এর অনুমতি নাও। Source-এর জানা অসঙ্গতি docs/KNOWN_LIMITATIONS.md-তে আছে, লুকিয়ে fix করো না।
12. একবার dry/offline যাচাই করে মালিককে সত্যিকারের প্রস্তুতির অবস্থা জানাও। নতুন producer কেবল cutover অনুমতির পর শুরু হবে।
