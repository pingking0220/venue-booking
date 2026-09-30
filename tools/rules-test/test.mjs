import { readFileSync } from 'fs';
import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';

const env = await initializeTestEnvironment({
  projectId: 'demo-venue',
  database: { rules: readFileSync('database.rules.json', 'utf8'), host: '127.0.0.1', port: 9000 },
});
const results = [];
async function t(name, p) {
  try { await p; results.push(['PASS', name]); } catch (e) { results.push(['FAIL', name, String(e.message || e).slice(0, 160)]); }
}
const user = (email, verified = true) => env.authenticatedContext(email.split('@')[0], { email, email_verified: verified }).database();
const T = user('teacher-a@lsps.tp.edu.tw'), T2 = user('teacher-z@lsps.tp.edu.tw');
const AP = user('approver@lsps.tp.edu.tw'), AD = user('it@lsps.tp.edu.tw'), GM = user('someone@gmail.com');
const D = '2026-10-05';
const rec = (by, status, extra = {}) => Object.assign({ title: '活動', by, name: 'x', unit: 'y', status, at: 1 }, extra);

async function seed() {
  await env.clearDatabase();
  await env.withSecurityRulesDisabled(async ctx => {
    await ctx.database().ref().set({
      roles: { 'it@lsps,tp,edu,tw': 'admin', 'teacher-a@lsps,tp,edu,tw': 'edu' },
      venue: {
        places: {
          free: { name: '視聽教室', active: true, needApproval: false },
          need: { name: '會議室', active: true, needApproval: true, approvers: { 'approver@lsps,tp,edu,tw': true } },
          other: { name: '穿堂', active: true, needApproval: true },
          closed: { name: '關閉', active: false, needApproval: false },
        },
        bk: { [D]: {
          need: { p1: rec('teacher-z@lsps.tp.edu.tw', 'wait') },
          other: { p1: rec('teacher-z@lsps.tp.edu.tw', 'wait') },
          free: { p2: rec('teacher-z@lsps.tp.edu.tw', 'ok'), p3: rec('teacher-a@lsps.tp.edu.tw', 'ok') },
        } },
      },
    });
  });
}
await seed();

// 讀取
await t('school can read bookings', assertSucceeds(T.ref('venue/bk').once('value')));
await t('gmail cannot read', assertFails(GM.ref('venue/bk').once('value')));
await t('unverified school email cannot read', assertFails(user('t@lsps.tp.edu.tw', false).ref('venue/bk').once('value')));
await t('school can read places', assertSucceeds(T.ref('venue/places').once('value')));

// 新借用
await t('book free venue as ok', assertSucceeds(T.ref(`venue/bk/${D}/free/p1`).set(rec('teacher-a@lsps.tp.edu.tw', 'ok'))));
await t('cannot self-approve on needApproval venue', assertFails(T.ref(`venue/bk/${D}/need/p2`).set(rec('teacher-a@lsps.tp.edu.tw', 'ok'))));
await t('book needApproval venue as wait', assertSucceeds(T.ref(`venue/bk/${D}/need/p2`).set(rec('teacher-a@lsps.tp.edu.tw', 'wait'))));
await t('free venue must be ok not wait', assertFails(T.ref(`venue/bk/${D}/free/p4`).set(rec('teacher-a@lsps.tp.edu.tw', 'wait'))));
await t('cannot overwrite existing slot', assertFails(T.ref(`venue/bk/${D}/free/p2`).set(rec('teacher-a@lsps.tp.edu.tw', 'ok'))));
await t('cannot book as someone else', assertFails(T.ref(`venue/bk/${D}/free/p5`).set(rec('teacher-z@lsps.tp.edu.tw', 'ok'))));
await t('cannot book inactive venue', assertFails(T.ref(`venue/bk/${D}/closed/p1`).set(rec('teacher-a@lsps.tp.edu.tw', 'ok'))));
await t('bad slot key rejected', assertFails(T.ref(`venue/bk/${D}/free/p9`).set(rec('teacher-a@lsps.tp.edu.tw', 'ok'))));
await t('bad date key rejected', assertFails(T.ref(`venue/bk/2026-1-5/free/p1`).set(rec('teacher-a@lsps.tp.edu.tw', 'ok'))));
await t('extra field rejected', assertFails(T.ref(`venue/bk/${D}/free/p6`).set(rec('teacher-a@lsps.tp.edu.tw', 'ok', { hack: 1 }))));
await t('title too long rejected', assertFails(T.ref(`venue/bk/${D}/free/p6`).set(rec('teacher-a@lsps.tp.edu.tw', 'ok', { title: 'x'.repeat(61) }))));
await t('empty title rejected', assertFails(T.ref(`venue/bk/${D}/free/p6`).set(rec('teacher-a@lsps.tp.edu.tw', 'ok', { title: '' }))));
await t('gmail cannot book', assertFails(GM.ref(`venue/bk/${D}/free/p7`).set(rec('someone@gmail.com', 'ok'))));
// 多格一次寫入：只要一格衝突就整批失敗
await t('multi-path with one conflict fails', assertFails(T.ref(`venue/bk/${D}/free`).update({ p7: rec('teacher-a@lsps.tp.edu.tw', 'ok'), p2: rec('teacher-a@lsps.tp.edu.tw', 'ok') })));
await t('...and the free slot stayed empty', (async () => { let ex = null; await env.withSecurityRulesDisabled(async c => { ex = (await c.database().ref(`venue/bk/${D}/free/p7`).once('value')).exists(); }); if (ex !== false) throw new Error('p7 was written: ' + ex); })());
await t('multi-path all free succeeds', assertSucceeds(T.ref('venue').update({ [`bk/${D}/free/p7`]: rec('teacher-a@lsps.tp.edu.tw', 'ok'), [`bk/2026-10-12/free/p7`]: rec('teacher-a@lsps.tp.edu.tw', 'ok') })));

// 取消
await t('cannot delete others booking', assertFails(T.ref(`venue/bk/${D}/free/p2`).remove()));
await t('can delete own booking', assertSucceeds(T.ref(`venue/bk/${D}/free/p3`).remove()));

// 審核
await t('non-approver cannot approve', assertFails(T2.ref(`venue/bk/${D}/need/p2/status`).set('ok')));
await t('owner cannot self-approve later', assertFails(T.ref(`venue/bk/${D}/need/p2/status`).set('ok')));
await t('approver approves', assertSucceeds(AP.ref(`venue/bk/${D}/need/p2/status`).set('ok')));
await t('approver cannot change title', assertFails(AP.ref(`venue/bk/${D}/need/p2/title`).set('改名')));
await t('approver rejects (deletes) in own venue', assertSucceeds(AP.ref(`venue/bk/${D}/need/p1`).remove()));
await t('approver cannot touch other venue', assertFails(AP.ref(`venue/bk/${D}/other/p1`).remove()));
await t('admin can delete anything', assertSucceeds(AD.ref(`venue/bk/${D}/other/p1`).remove()));
await t('admin approves where no approver', assertSucceeds(AD.ref(`venue/bk/${D}/free/p1/status`).set('ok')));

// 場地與設定
await t('teacher cannot edit places', assertFails(T.ref('venue/places/free/needApproval').set(true)));
await t('teacher cannot make self approver', assertFails(T.ref('venue/places/need/approvers/teacher-a@lsps,tp,edu,tw').set(true)));
await t('admin edits places', assertSucceeds(AD.ref('venue/places/new1').set({ name: '新場地', active: false, needApproval: true })));
await t('teacher cannot edit config', assertFails(T.ref('venue/config/semesterEnd').set('2027-01-20')));
await t('admin edits config', assertSucceeds(AD.ref('venue/config/semesterEnd').set('2027-01-20')));

// 通知
await t('anyone school can notify others', assertSucceeds(AP.ref('venue/notice/teacher-a@lsps,tp,edu,tw/n1').set({ text: '已退回', at: 1 })));
await t('cannot read others notices', assertFails(T2.ref('venue/notice/teacher-a@lsps,tp,edu,tw').once('value')));
await t('owner reads own notices', assertSucceeds(T.ref('venue/notice/teacher-a@lsps,tp,edu,tw').once('value')));
await t('non-owner cannot delete notice', assertFails(T2.ref('venue/notice/teacher-a@lsps,tp,edu,tw/n1').remove()));
await t('cannot overwrite existing notice', assertFails(T2.ref('venue/notice/teacher-a@lsps,tp,edu,tw/n1').set({ text: '假的', at: 2 })));
await t('owner deletes own notice', assertSucceeds(T.ref('venue/notice/teacher-a@lsps,tp,edu,tw/n1').remove()));
await t('gmail cannot notify', assertFails(GM.ref('venue/notice/teacher-a@lsps,tp,edu,tw/n2').set({ text: 'spam', at: 1 })));

// 頒獎座位系統既有規則不受影響
await t('award: own role readable', assertSucceeds(T.ref('roles/teacher-a@lsps,tp,edu,tw').once('value')));
await t('award: others role not readable', assertFails(T.ref('roles/it@lsps,tp,edu,tw').once('value')));

await env.cleanup();
results.forEach(r => console.log(r.join(' ')));
console.log(results.some(r => r[0] === 'FAIL') ? 'FAILED' : 'ALL PASSED');
process.exit(0);
