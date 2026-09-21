import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT = "C:/Users/28646/Documents/ChatGPT/New project/PGRR/outputs/student/PGRR_教授交流讨论提纲_简洁版.pptx";
const BUILD = "C:/Users/28646/Documents/ChatGPT/New project/PGRR/outputs/student/meeting_ppt_build";
const W = 1280, H = 720;
const C = { navy: "#12355B", teal: "#0F8B8D", ink: "#17212B", muted: "#536579", pale: "#F5F8FA", line: "#D8E1E8", white: "#FFFFFF", green: "#31A58B", orange: "#E8913A" };

async function writeBlob(path, blob) { await fs.writeFile(path, new Uint8Array(await blob.arrayBuffer())); }
function box(slide, x, y, w, h, fill, radius = "rounded-xl", line = "none") {
  return slide.shapes.add({ geometry: "roundRect", position: { left:x, top:y, width:w, height:h }, fill, line: { style:"solid", fill:line === "none" ? "none" : line, width: line === "none" ? 0 : 1 }, borderRadius: radius });
}
function text(slide, value, x, y, w, h, size=22, color=C.ink, bold=false, align="left") {
  const s = slide.shapes.add({ geometry:"textbox", position:{left:x,top:y,width:w,height:h}, fill:"none", line:{style:"solid",fill:"none",width:0} });
  s.text = value; s.text.style = { fontSize:size, color, bold, alignment:align, fontFace:"Aptos" }; return s;
}
function header(slide, title, n) {
  text(slide, "PGRR · 研究交流", 68, 28, 300, 24, 14, C.teal, true);
  text(slide, title, 68, 70, 1140, 50, 36, C.navy, true);
  slide.shapes.add({ geometry:"rect", position:{left:68,top:132,width:1144,height:2},fill:C.line,line:{style:"solid",fill:"none",width:0} });
  text(slide, String(n).padStart(2,"0"), 1150, 668, 58, 20, 13, C.muted, true, "right");
}
function bulletList(slide, items, x, y, w, fs=23, color=C.ink, gap=50) {
  items.forEach((v,i) => { text(slide, "•", x, y+i*gap, 20, 30, fs, C.teal, true); text(slide, v, x+30, y+i*gap, w-30, 38, fs, color); });
}
function tag(slide, value, x, y, w, fill=C.teal) { box(slide,x,y,w,34,fill,"rounded-full"); text(slide,value,x,y+6,w,20,14,C.white,true,"center"); }
function arrow(slide, x1, y1, x2, y2) { const l=slide.shapes.add({geometry:"line",position:{left:Math.min(x1,x2),top:Math.min(y1,y2),width:Math.abs(x2-x1),height:Math.abs(y2-y1)},line:{style:"solid",fill:C.teal,width:3,beginArrowType:"none",endArrowType:"triangle"}}); return l; }
function node(slide, label, x,y,w,h, fill=C.white, ink=C.navy) { box(slide,x,y,w,h,fill,"rounded-xl",C.line); text(slide,label,x+12,y+14,w-24,h-24,20,ink,true,"center"); }

async function main() {
  await fs.mkdir(BUILD,{recursive:true});
  const p = Presentation.create({slideSize:{width:W,height:H}});
  // 1
  { const s=p.slides.add(); s.background.fill=C.pale;
    text(s,"PGRR 项目复现进展\n与后续实验讨论",68,130,760,170,52,C.navy,true);
    text(s,"面向教授交流的工作汇报与决策问题",72,326,650,36,24,C.muted);
    tag(s,"简洁讨论版",72,395,116,C.teal);
    box(s,890,130,250,350,C.navy); text(s,"PGRR",930,190,170,55,42,C.white,true,"center"); text(s,"Planning-Guided\nFailure-Triggered\nRecovery & Rejoin",922,272,186,100,20,"#DCEBF5",false,"center");
    text(s,"汇报人：__________    日期：__________",72,620,520,24,17,C.muted);
  }
  // 2
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"希望本次交流明确的四个决策",2);
    const items=[["新场景的研究问题","新环境应验证哪一种困难交互？"],["公平对照与数据划分","如何扩展而不触碰冻结测试集？"],["DAgger 诊断路径","后续候选变差应先查什么？"],["重构最小边界","哪些模块先拆、哪些接口绝不动？"]];
    items.forEach((a,i)=>{const x=76+(i%2)*568,y=180+Math.floor(i/2)*190; box(s,x,y,520,140,C.pale); text(s,`0${i+1}`,x+24,y+26,54,34,30,C.teal,true); text(s,a[0],x+92,y+27,370,28,25,C.navy,true); text(s,a[1],x+92,y+72,390,34,18,C.muted);});
    text(s,"目标不是重复跑一次，而是形成可解释、可写入论文的独立对照实验。",76,610,1050,34,23,C.ink,true);
  }
  // 3
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"我们已完成：环境、离线训练与在线恢复链路验证",3);
    const cols=[["离线环境","Python 3.10\n动作空间、掩码、专家标签与 BC 测试通过"],["在线环境","WSL2 · Ubuntu 22.04\nROS2 Humble · Arena · Docker"],["构建与冒烟","make arena / build / smoke 通过\n恢复管理器 ROS 冒烟通过"]];
    cols.forEach((a,i)=>{const x=76+i*374; box(s,x,198,330,250,i===2 ? "#EAF6F3" : C.pale); text(s,a[0],x+26,232,275,34,27,C.navy,true); text(s,a[1],x+26,292,270,100,19,C.muted); tag(s,"已验证",x+26,405,82,C.green);});
    text(s,"这些结果是“环境与链路可运行”的证据，不替代论文中的最终统计结果。",76,600,1060,32,21,C.orange,true);
  }
  // 4
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"在线恢复管理器：已验证临时目标与原任务目标的恢复",4);
    const y=274; arrow(s,282,y+35,370,y+35); arrow(s,572,y+35,660,y+35); arrow(s,862,y+35,950,y+35);
    node(s,"检测到失败风险",84,y,198,72,"#F1F7FA"); node(s,"临时恢复目标\n(0.966, 0.500)",370,y,202,72,"#EAF6F3"); node(s,"受限恢复执行\n共 5 次决策",660,y,202,72,"#F1F7FA"); node(s,"恢复原任务目标\n(5.0, 0.0)",950,y,202,72,"#EAF6F3");
    text(s,"意义：项目的“恢复后回到原路线”核心闭环已经在 ROS 冒烟脚本中跑通。",84,445,1060,34,24,C.navy,true);
    text(s,"备注：出现过 QoS 兼容性警告，但冒烟脚本以 PASS 结束；需在更复杂的闭环场景中继续观察。",84,500,1060,54,19,C.muted);
  }
  // 5
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"PGRR 的作用：正常时由 DWB 行驶，失败时才短暂介入",5);
    arrow(s,274,285,374,285); arrow(s,565,285,665,205); arrow(s,565,305,665,385); arrow(s,860,205,965,285); arrow(s,860,385,965,285);
    node(s,"观测\n激光、路径、目标、历史",76,248,198,76); node(s,"持续失败？\n规则触发",374,248,191,76,"#FFF7EC"); node(s,"否：Nav2 DWB\n正常导航",665,168,195,74,"#F1F7FA"); node(s,"是：PGRR\n掩码 + 策略",665,348,195,74,"#EAF6F3"); node(s,"命令/目标复用\n完成后回归 DWB",965,248,205,76,"#F1F7FA");
    text(s,"PGRR 不取代 DWB；它是“失败触发、短时、有边界”的恢复层。",76,540,1050,34,24,C.navy,true);
  }
  // 6
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"下一步应在独立新场景中检验：安全与完成的提升是否可迁移",6);
    text(s,"研究问题",82,184,160,28,25,C.teal,true); text(s,"当拥挤、遮挡或路径冲突方式变化时，PGRR 是否仍能以可接受的效率代价减少碰撞并提升到达？",82,228,1040,62,26,C.navy,true);
    const metrics=[["安全","碰撞率、最近距离、急停/干预"],["完成","到达率、超时率、规划失败率"],["代价","时长、路径长度、角加速度/平滑性"]];
    metrics.forEach((m,i)=>{const x=82+i*365; box(s,x,360,320,142,C.pale); text(s,m[0],x+22,386,100,28,24,C.navy,true); text(s,m[1],x+22,430,272,44,18,C.muted);});
    text(s,"边界：不在已冻结的 moderate_v6 测试集上调参；新实验应使用独立的场景与划分。",82,576,1070,28,20,C.orange,true);
  }
  // 7
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"建议优先扩展四类“具有论文价值”的新交互场景",7);
    const scenes=[["窄走廊对向通行","侧向让行空间有限，考验临时子目标"],["T 路口横穿与遮挡","转角后突然出现动态行人"],["门口 / 电梯口群体阻塞","等待、绕行与重新规划的取舍"],["静态障碍 + 横穿行人","多因素叠加，避免只测单一困难"]];
    scenes.forEach((a,i)=>{const x=76+(i%2)*570,y=175+Math.floor(i/2)*190; box(s,x,y,530,145,C.pale); text(s,`场景 ${i+1}`,x+24,y+25,92,24,17,C.teal,true); text(s,a[0],x+24,y+58,460,30,25,C.navy,true); text(s,a[1],x+24,y+98,466,24,18,C.muted);});
  }
  // 8
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"新增实验必须先锁定公平性：按场景与种子划分，而非按帧划分",8);
    const x=[92,353,614,875], labels=["新场景库\n地图 / 行人轨迹 / 密度", "训练集\n专家标签、BC、DAgger", "验证集\n选模型、定阈值、做消融", "独立保留测试\n仅做最终对照" ];
    for(let i=0;i<4;i++){if(i<3)arrow(s,x[i]+186,315,x[i+1]-20,315); node(s,labels[i],x[i],272,186,88,i===3 ? "#FFF7EC" : (i===2 ? "#EAF6F3" : C.pale));}
    text(s,"同一条件下比较 Base / Standard / Heuristic / BC / PGRR，并保留每一次 episode 的终止原因。",92,470,1060,34,23,C.navy,true);
    text(s,"需要教授确认：新场景是否采用“同一地图新交互”还是“新地图 + 新交互”的泛化层级？",92,542,1060,34,20,C.muted);
  }
  // 9
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"DAgger 第二次候选在验证上更差：先做诊断，不应直接下结论",9);
    text(s,"当前准确表述",82,182,220,30,25,C.teal,true); text(s,"“后续 DAgger 候选的验证表现不如已选模型。”",82,225,1000,38,28,C.navy,true);
    const causes=[["经典过拟合","训练表现继续变好，但验证表现下降"],["数据覆盖失衡","少数高风险状态被重复采样或类别分布偏移"],["分布/标签变化","新收集状态、专家标签或掩码的统计性质改变"],["配置差异","轮次、权重、早停或验证集配置并不等价"]];
    causes.forEach((a,i)=>{const x=82+(i%2)*560,y=330+Math.floor(i/2)*125; text(s,a[0],x,y,175,26,21,C.navy,true); text(s,a[1],x,y+34,470,48,17,C.muted);});
  }
  // 10
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"DAgger 改进应从可复现诊断开始，再在新训练/验证集上做受控比较",10);
    const steps=[["1", "比较曲线", "BC、DAgger-1、后续候选：训练与验证 loss / top-1"],["2", "查数据分布", "动作类别、掩码可行动作数、场景覆盖、专家 regret"],["3", "查闭环失败", "碰撞、超时、规划失败在何种状态与场景集中出现"],["4", "受控改进", "重采样、类别平衡、混合比例、早停；每次只改一个变量"]];
    steps.forEach((a,i)=>{const y=172+i*102; text(s,a[0],86,y,36,30,28,C.teal,true); text(s,a[1],140,y,190,28,22,C.navy,true); text(s,a[2],340,y,760,40,19,C.muted); if(i<3)s.shapes.add({geometry:"rect",position:{left:140,top:y+68,width:960,height:1},fill:C.line,line:{style:"solid",fill:"none",width:0}});});
    text(s,"所有模型选择只看验证集；独立保留测试集只在方案锁定后运行一次。",86,600,1050,30,21,C.orange,true);
  }
  // 11
  { const s=p.slides.add(); s.background.fill=C.white; header(s,"作业二、三的下一步：先最小重构，再把研究设计划成图",11);
    const left=[["观察构建器","整理传感器、进度、路径与历史状态"],["决策协调器","触发、动作掩码、策略选择、状态机"],["ROS 适配层","订阅/发布/参数/时钟，保持行为不变"]];
    left.forEach((a,i)=>{const y=190+i*110; box(s,78,y,452,80,C.pale); text(s,a[0],100,y+16,150,25,21,C.navy,true); text(s,a[1],100,y+46,390,20,16,C.muted);});
    text(s,"作业三图示",650,190,220,28,24,C.teal,true); bulletList(s,["算法框架：DWB 与 PGRR 的分工和回归路径","任务场景：行人、障碍物、起终点、冲突区域","实验流程：数据 → 标签 → 训练 → 验证 → 保留测试"],650,248,500,20,C.ink,72);
    text(s,"重构原则：先保持 25 个动作 ID、观察/掩码形状和 ROS 接口不变，再用单元测试证明行为一致。",78,575,1065,35,20,C.orange,true);
  }
  // 12
  { const s=p.slides.add(); s.background.fill=C.pale; header(s,"希望教授给予的四项指导，以及会后可执行的第一步",12);
    const qs=["新场景优先选择哪 2–3 类？研究问题如何收敛？","训练 / 验证 / 保留测试应如何定义泛化层级？","DAgger 诊断最值得先看哪些指标与消融？","模块化重构的最小可接受范围与代码审查重点？"];
    bulletList(s,qs,80,175,1030,22,C.ink,74);
    box(s,80,510,1060,95,C.navy); text(s,"会后第一步：写出场景参数表与数据划分方案 → 请教授确认 → 再启动独立实验。",110,540,1000,33,24,C.white,true,"center");
  }
  for (const [i,s] of p.slides.items.entries()) await writeBlob(`${BUILD}/slide-${String(i+1).padStart(2,"0")}.png`, await p.export({slide:s,format:"png",scale:1}));
  await writeBlob(`${BUILD}/montage.webp`, await p.export({format:"webp",montage:true,scale:1}));
  const f=await PresentationFile.exportPptx(p); await f.save(OUT);
}
main().catch(e=>{console.error(e);process.exitCode=1;});
