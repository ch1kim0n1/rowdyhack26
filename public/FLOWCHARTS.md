# Appraisal Job: system flowcharts

Business-readable views. Render on GitHub, mermaid.live, or any Mermaid-enabled slide tool.

## 1. What it does, in one line

```mermaid
flowchart LR
    A["Hold up any object"] --> B["Camera sees it"]
    B --> C["AI names it and reads the details<br/>even badges and keycards"]
    C --> D["Prices it from real sold listings"]
    D --> E["Files it in the case"]
    E --> F["Live on every screen:<br/>big show, wrist watch, scout bot"]
    F --> G["One button press<br/>the lineup reveals"]
    G --> H["Owner's Defender Report:<br/>what was taken, what it cost"]
    style A fill:#f6e8c9
    style H fill:#d4edda
    style G fill:#f8d7da
```

## 2. One hub, many devices

```mermaid
flowchart TB
    HUB["The Hub<br/>Raspberry Pi in a hat"]
    HUB --> A["Big screen<br/>the appraisal show, live"]
    HUB --> B["Wrist watch<br/>running take, still recording?"]
    HUB --> C["Scout rover<br/>drives off, finds loot, reports back"]
    HUB --> D["Crew phone<br/>dispatch console, radio call"]
    HUB --> E["Receipt printer + voice<br/>theatrical touches"]
    style HUB fill:#cfe2ff
```

## 3. Why it is hard

```mermaid
flowchart LR
    subgraph EASY["What a demo usually does"]
        E1["Point camera"] --> E2["Show a label"]
    end
    subgraph THIS["What this rig actually does"]
        T1["Sees the object"] --> T2["Identifies it,<br/>no internet needed"]
        T2 --> T3["Prices it from<br/>real market data"]
        T3 --> T4["Plans the heist:<br/>bag size, seconds, risk"]
        T4 --> T5["Files evidence<br/>the victim can read"]
    end
    style THIS fill:#d4edda
    style EASY fill:#e2e3e5
```

## Stack badges

Skillicons strip, one image:

```markdown
![stack](https://skillicons.dev/icons?i=python,flask,opencv,arduino,raspberrypi,js,html,css,docker,railway,githubactions)
```

Shield badges, fuller list:

```markdown
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask%20%2B%20Waitress-000?logo=flask&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-headless-5C3EE8?logo=opencv&logoColor=white)
![ESP32](https://img.shields.io/badge/ESP32-FreeRTOS-E7352C?logo=espressif&logoColor=white)
![OpenAI](https://img.shields.io/badge/Vision%20%2B%20Whisper-OpenAI-412991?logo=openai&logoColor=white)
![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway&logoColor=white)
```
