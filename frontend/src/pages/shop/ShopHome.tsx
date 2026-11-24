import { RobotOutlined, SearchOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Empty, Image, Input, Space, Spin, Typography } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { listCatalogCategories, listCatalogProducts } from '../../api/catalog';
import { useAuthStore } from '../../stores/authStore';
import { errorMessage } from '../../utils/error';

const PRODUCT_PLACEHOLDER = '/products/placeholder.svg';

function priceLabel(from: string | null, to: string | null): string {
  if (!from) return '暂无报价';
  if (!to || from === to) return `¥${from}`;
  return `¥${from} 起`;
}

export function ShopHomePage() {
  const { user, status } = useAuthStore();
  const [categoryId, setCategoryId] = useState<number | undefined>();
  const [search, setSearch] = useState('');

  const categories = useQuery({
    queryKey: ['catalog-categories'],
    queryFn: listCatalogCategories,
  });
  const products = useQuery({
    queryKey: ['catalog-products', categoryId, search],
    queryFn: () =>
      listCatalogProducts({
        category_id: categoryId,
        keyword: search || undefined,
        page_size: 50,
      }),
  });

  return (
    <div className="shop-page">
      <section className="shop-hero">
        <div>
          <Typography.Text className="shop-eyebrow">QINGFENG DIGITAL</Typography.Text>
          <Typography.Title level={1}>找到适合你的数码产品</Typography.Title>
          <Typography.Paragraph>
            手机、电脑、平板与智能穿戴，清风数码为你精选。
          </Typography.Paragraph>
          <Space wrap>
            <Link to="/shop/assistant">
              <Button type="primary" size="large" icon={<RobotOutlined />}>
                问 AI 导购
              </Button>
            </Link>
            {status !== 'authenticated' ? (
              <Link to="/login">
                <Button size="large">登录后咨询</Button>
              </Link>
            ) : null}
          </Space>
          {status === 'authenticated' && user ? (
            <Typography.Paragraph className="shop-hero-note">
              你好，{user.email}。可以问我预算、用途、库存或售后政策。
            </Typography.Paragraph>
          ) : null}
        </div>
        <div className="shop-hero-badge">
          <RobotOutlined />
          <span>AI 导购</span>
          <small>真实商品 · 实时库存</small>
        </div>
      </section>

      <div className="shop-toolbar">
        <Space wrap>
          <Button type={categoryId === undefined ? 'primary' : 'default'} onClick={() => setCategoryId(undefined)}>
            全部
          </Button>
          {(categories.data ?? []).map((category) => (
            <Button
              key={category.id}
              type={categoryId === category.id ? 'primary' : 'default'}
              onClick={() => setCategoryId(category.id)}
            >
              {category.name}
            </Button>
          ))}
        </Space>
        <Input.Search
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索商品"
          style={{ maxWidth: 320 }}
          onSearch={(value) => setSearch(value)}
          enterButton
        />
      </div>

      {products.error ? <Alert type="error" showIcon message={errorMessage(products.error)} /> : null}
      {categories.error ? <Alert type="warning" showIcon message={errorMessage(categories.error)} /> : null}

      {products.isLoading ? (
        <div className="shop-loading">
          <Spin />
        </div>
      ) : products.data?.items.length ? (
        <div className="shop-grid">
          {products.data.items.map((product) => (
            <Card key={product.id} className="shop-product-card" hoverable>
              <Link to={`/shop/products/${product.product_no}`}>
                <Image
                  src={product.image_url || PRODUCT_PLACEHOLDER}
                  fallback={PRODUCT_PLACEHOLDER}
                  alt={product.name}
                  height={190}
                  width="100%"
                  preview={false}
                  style={{ objectFit: 'cover', borderRadius: 12 }}
                />
              </Link>
              <Typography.Text type="secondary">{product.category_name}</Typography.Text>
              <Typography.Title level={4}>
                <Link to={`/shop/products/${product.product_no}`}>{product.name}</Link>
              </Typography.Title>
              <div className="shop-price-row">
                <strong>{priceLabel(product.price_from, product.price_to)}</strong>
                <Typography.Text type={product.available_stock > 0 ? 'success' : 'danger'}>
                  {product.available_stock > 0 ? `现货 ${product.available_stock}` : '暂时缺货'}
                </Typography.Text>
              </div>
              <Space wrap>
                <Link to={`/shop/products/${product.product_no}`}>
                  <Button type="primary">查看详情</Button>
                </Link>
                <Link to="/shop/assistant">
                  <Button icon={<RobotOutlined />}>问 AI</Button>
                </Link>
              </Space>
            </Card>
          ))}
        </div>
      ) : (
        <Empty description="没有找到符合条件的商品" />
      )}
    </div>
  );
}
