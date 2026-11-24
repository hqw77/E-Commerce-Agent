import { RobotOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Image,
  Input,
  InputNumber,
  Modal,
  Space,
  Tag,
  Typography,
} from 'antd';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getCatalogProduct } from '../../api/catalog';
import { createMyOrder } from '../../api/customerOrders';
import { useAuthStore } from '../../stores/authStore';
import { errorMessage } from '../../utils/error';
import { formatMoney } from '../../utils/format';
import type { SkuDetail } from '../../types/product';

const PRODUCT_PLACEHOLDER = '/products/placeholder.svg';

interface BuyFormValues {
  receiver_name: string;
  receiver_phone: string;
  receiver_address: string;
  quantity: number;
}

export function ShopProductPage() {
  const { productNo } = useParams<{ productNo: string }>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { status } = useAuthStore();
  const [buySku, setBuySku] = useState<SkuDetail | null>(null);
  const [buying, setBuying] = useState(false);
  const [buyForm] = Form.useForm<BuyFormValues>();
  const query = useQuery({
    queryKey: ['catalog-product', productNo],
    queryFn: () => getCatalogProduct(productNo!),
    enabled: Boolean(productNo),
  });

  function openBuy(sku: SkuDetail) {
    if (status !== 'authenticated') {
      navigate('/login');
      return;
    }
    setBuySku(sku);
    buyForm.setFieldsValue({ quantity: 1 });
  }

  async function submitBuy(values: BuyFormValues) {
    if (!buySku) return;
    setBuying(true);
    try {
      const order = await createMyOrder({
        items: [{ sku_code: buySku.sku_code, quantity: values.quantity }],
        receiver_name: values.receiver_name,
        receiver_phone: values.receiver_phone,
        receiver_address: values.receiver_address,
        customer_remark: '商城立即购买',
        idempotency_key: crypto.randomUUID(),
      });
      message.success('订单已提交');
      setBuySku(null);
      navigate(`/shop/orders/${order.order_no}`);
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setBuying(false);
    }
  }

  if (!productNo) return <Alert type="error" showIcon message="无效的商品编号" />;
  if (query.error) return <Alert type="error" showIcon message={errorMessage(query.error)} />;
  if (!query.data) return <Card loading />;

  const product = query.data;
  const activeSkus = product.skus.filter((sku) => sku.status === 'ACTIVE');
  const priceValues = activeSkus.map((sku) => Number(sku.price));
  const minPrice = priceValues.length ? Math.min(...priceValues) : null;
  const maxPrice = priceValues.length ? Math.max(...priceValues) : null;
  const availableStock = activeSkus.reduce(
    (total, sku) => total + (sku.inventory?.available_quantity ?? 0),
    0,
  );

  return (
    <div className="shop-page">
      <Space>
        <Button onClick={() => navigate('/shop')}>返回商城</Button>
        <Link to="/shop/assistant">
          <Button type="primary" icon={<RobotOutlined />}>
            问 AI 导购
          </Button>
        </Link>
      </Space>

      <Card className="shop-detail-card">
        <div className="shop-detail">
          <Image
            src={product.image_url || PRODUCT_PLACEHOLDER}
            fallback={PRODUCT_PLACEHOLDER}
            alt={product.name}
            width={360}
            height={360}
            style={{ objectFit: 'cover', borderRadius: 16 }}
          />
          <div className="shop-detail-info">
            <Typography.Text type="secondary">
              {product.category_name} · {product.product_no}
            </Typography.Text>
            <Typography.Title level={2}>{product.name}</Typography.Title>
            <Typography.Paragraph type="secondary">
              {product.description || '暂无商品描述'}
            </Typography.Paragraph>
            <div className="shop-detail-price">
              {minPrice ? formatMoney(minPrice) : '暂无报价'}
              {maxPrice && minPrice !== maxPrice ? ` 起` : null}
            </div>
            <Space wrap>
              <Tag color={availableStock > 0 ? 'green' : 'red'}>
                {availableStock > 0 ? `现货 ${availableStock}` : '暂时缺货'}
              </Tag>
              <Tag>{activeSkus.length} 个规格</Tag>
            </Space>
            <Descriptions column={1} size="small" className="shop-detail-meta">
              <Descriptions.Item label="商品编号">{product.product_no}</Descriptions.Item>
              <Descriptions.Item label="分类">{product.category_name}</Descriptions.Item>
              <Descriptions.Item label="状态">{product.status === 'ACTIVE' ? '在售' : product.status}</Descriptions.Item>
            </Descriptions>
          </div>
        </div>
      </Card>

      <Card className="shop-detail-card" title="选择规格">
        <div className="shop-sku-grid">
          {activeSkus.map((sku: SkuDetail) => (
            <div key={sku.id} className="shop-sku-card">
              <Typography.Text strong>{sku.sku_code}</Typography.Text>
              <Typography.Paragraph type="secondary">
                {Object.entries(sku.attributes)
                  .map(([key, value]) => `${key}: ${value}`)
                  .join(' / ') || '默认规格'}
              </Typography.Paragraph>
              <Space wrap>
                <strong>{formatMoney(sku.price)}</strong>
                <Tag color={(sku.inventory?.available_quantity ?? 0) > 0 ? 'green' : 'red'}>
                  可用 {sku.inventory?.available_quantity ?? 0}
                </Tag>
                <Button
                  type="primary"
                  disabled={(sku.inventory?.available_quantity ?? 0) <= 0}
                  onClick={() => openBuy(sku)}
                >
                  立即购买
                </Button>
              </Space>
            </div>
          ))}
        </div>
      </Card>

      <Alert
        type="info"
        showIcon
        message="需要推荐或售后帮助？"
        description="可以打开 AI 导购，询问预算、用途、库存或订单问题。"
        action={
          <Link to="/shop/assistant">
            <Button>去咨询</Button>
          </Link>
        }
      />

      <Modal
        title="确认订单"
        open={Boolean(buySku)}
        onCancel={() => setBuySku(null)}
        onOk={() => buyForm.submit()}
        confirmLoading={buying}
        okText="提交订单"
        destroyOnHidden
      >
        {buySku ? (
          <Typography.Paragraph>
            {product.name} · {buySku.sku_code} · {formatMoney(buySku.price)}
          </Typography.Paragraph>
        ) : null}
        <Form form={buyForm} layout="vertical" onFinish={submitBuy}>
          <Form.Item
            name="receiver_name"
            label="收货人"
            rules={[{ required: true, message: '请输入收货人' }]}
          >
            <Input placeholder="请输入收货人" />
          </Form.Item>
          <Form.Item
            name="receiver_phone"
            label="手机号"
            rules={[{ required: true, message: '请输入手机号' }]}
          >
            <Input placeholder="请输入手机号" />
          </Form.Item>
          <Form.Item
            name="receiver_address"
            label="收货地址"
            rules={[{ required: true, message: '请输入收货地址' }]}
          >
            <Input.TextArea rows={2} placeholder="请输入详细地址" />
          </Form.Item>
          <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
            <InputNumber min={1} max={buySku?.inventory?.available_quantity ?? 1} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
        <Alert
          type="info"
          showIcon
          message="当前版本暂不接入支付"
          description="提交后生成待发货订单，由运营后台处理发货。"
        />
      </Modal>
    </div>
  );
}
