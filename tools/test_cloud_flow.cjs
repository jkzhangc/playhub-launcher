const assert=require('assert');
const {loginRequired,valid}=require('./cloud_bridge.cjs');
assert.equal(loginRequired("download_need_signin: true, userName: ''"),true);
assert.equal(loginRequired("download_need_signin: true, userName: 'authorized-user'"),false);
assert.equal(loginRequired('download_need_signin: false'),false);
assert.equal(valid('https://www.jianguoyun.com/d/login','nutstore'),'https://www.jianguoyun.com/d/login');
for(const url of ['https://www.jianguoyun.com.evil.invalid/d/login','http://www.jianguoyun.com/d/login','https://user:pass@www.jianguoyun.com/d/login'])assert.throws(()=>valid(url,'nutstore'));
console.log('Cloud flow: 7 login and official-domain boundary checks passed.');
