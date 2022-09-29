let vm = new Vue({
    el: '#app',
    delimiters: ['[[', ']]'],
    data: {
        username: getCookie('username'),
    },
    mounted(){
    },
    methods: {
        oper_btn_click(order_id, status){
            if (status == '1') {
                // 待支付
                let url = '/payment/' + order_id + '/';
                axios.get(url, {
                    responseType: 'json'
                })
                    .then(response => {
                        if (response.data.code == '0') {
                            location.href = response.data.alipay_url;
                        } else if (response.data.code == '4101') {
                            location.href = '/login/?next=/orders/info/1/';
                        } else {
                            console.log(response.data);
                            alert(response.data.errmsg);
                        }
                    })
                    .catch(error => {
                        console.log(error.response);
                    });
            } else if (status == '4') {
                // 待评价
                location.href = '/orders/comment/?order_id=' + order_id;
                // location.href = '/';
            } else {
                // 其他：待收货...
                location.href = '/';
            }
        },
    }
});